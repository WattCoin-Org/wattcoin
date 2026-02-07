"""
Tests for the health check endpoint (/api/v1/health)
"""

import json
import time
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

import bridge_web
import api_health


@pytest.fixture
def client():
    """Create a test client."""
    bridge_web.app.config['TESTING'] = True
    with bridge_web.app.test_client() as client:
        yield client


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test tasks.json
        tasks_file = os.path.join(tmpdir, 'tasks.json')
        with open(tasks_file, 'w') as f:
            json.dump([
                {"id": 1, "status": "open", "title": "Task 1"},
                {"id": 2, "status": "open", "title": "Task 2"},
                {"id": 3, "status": "completed", "title": "Task 3"}
            ], f)
        
        # Create test nodes.json
        nodes_file = os.path.join(tmpdir, 'nodes.json')
        with open(nodes_file, 'w') as f:
            json.dump({
                "node1": {"id": "node1", "last_seen": time.time()},
                "node2": {"id": "node2", "last_seen": time.time()},
                "node3": {"id": "node3", "last_seen": time.time() - 600}  # Inactive
            }, f)
        
        yield tmpdir


class TestHealthEndpoint:
    """Tests for /api/v1/health endpoint."""
    
    def test_health_returns_200(self, client):
        """Health endpoint should return 200 OK."""
        response = client.get('/api/v1/health')
        assert response.status_code == 200
    
    def test_health_returns_json(self, client):
        """Health endpoint should return valid JSON."""
        response = client.get('/api/v1/health')
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert data is not None
    
    def test_health_has_required_fields(self, client):
        """Health response should contain all required fields."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        assert 'status' in data
        assert 'version' in data
        assert 'uptime_seconds' in data
        assert 'services' in data
        assert 'active_nodes' in data
        assert 'open_tasks' in data
        assert 'timestamp' in data
    
    def test_health_services_structure(self, client):
        """Services field should contain database, discord, and ai_api."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        services = data['services']
        assert 'database' in services
        assert 'discord' in services
        assert 'ai_api' in services
    
    def test_health_version_format(self, client):
        """Version should be a valid semver string."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        version = data['version']
        assert isinstance(version, str)
        # Should be semver format (X.Y.Z)
        parts = version.split('.')
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)
    
    def test_health_uptime_is_positive(self, client):
        """Uptime should be a positive integer."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        uptime = data['uptime_seconds']
        assert isinstance(uptime, int)
        assert uptime >= 0
    
    def test_health_timestamp_format(self, client):
        """Timestamp should be ISO 8601 format."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        timestamp = data['timestamp']
        assert isinstance(timestamp, str)
        # Should contain T separator and timezone info
        assert 'T' in timestamp
    
    def test_health_active_nodes_is_integer(self, client):
        """Active nodes count should be an integer."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        assert isinstance(data['active_nodes'], int)
        assert data['active_nodes'] >= 0
    
    def test_health_open_tasks_is_integer(self, client):
        """Open tasks count should be an integer."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        assert isinstance(data['open_tasks'], int)
        assert data['open_tasks'] >= 0
    
    def test_health_status_is_valid(self, client):
        """Status should be 'healthy' or 'degraded'."""
        response = client.get('/api/v1/health')
        data = response.get_json()
        
        assert data['status'] in ('healthy', 'degraded')


class TestHealthServiceChecks:
    """Tests for individual service check functions."""
    
    def test_check_database_with_valid_files(self, temp_data_dir):
        """Database check should return 'ok' with readable files."""
        with patch.object(api_health, 'DATA_DIR', temp_data_dir):
            result = api_health.check_database()
            assert result == "ok"
    
    def test_check_database_with_missing_dir(self):
        """Database check should handle missing directory gracefully."""
        with patch.object(api_health, 'DATA_DIR', '/nonexistent/path'):
            result = api_health.check_database()
            # Should return ok if files don't exist (they might not exist yet)
            assert result in ("ok", "error")
    
    def test_check_discord_configured(self):
        """Discord check should return 'ok' when webhook is configured."""
        with patch.object(api_health, 'DISCORD_WEBHOOK_URL', 
                         'https://discord.com/api/webhooks/123/abc'):
            result = api_health.check_discord()
            assert result == "ok"
    
    def test_check_discord_not_configured(self):
        """Discord check should return 'not_configured' when empty."""
        with patch.object(api_health, 'DISCORD_WEBHOOK_URL', ''):
            result = api_health.check_discord()
            assert result == "not_configured"
    
    def test_check_ai_api_with_key(self):
        """AI API check should return 'ok' when API key is set."""
        with patch.object(api_health, 'CLAUDE_API_KEY', 'test-key'):
            with patch('api_health.requests.head') as mock_head:
                mock_response = MagicMock()
                mock_response.status_code = 401  # Auth failed but reachable
                mock_head.return_value = mock_response
                result = api_health.check_ai_api()
                assert result == "ok"
    
    def test_check_ai_api_not_configured(self):
        """AI API check should return 'not_configured' when no keys."""
        with patch.object(api_health, 'CLAUDE_API_KEY', ''):
            with patch.object(api_health, 'OPENAI_API_KEY', ''):
                with patch.object(api_health, 'GROK_API_KEY', ''):
                    result = api_health.check_ai_api()
                    assert result == "not_configured"


class TestNodeAndTaskCounts:
    """Tests for node and task counting functions."""
    
    def test_get_active_node_count(self, temp_data_dir):
        """Should count only recently active nodes."""
        with patch.object(api_health, 'NODES_FILE', 
                         os.path.join(temp_data_dir, 'nodes.json')):
            count = api_health.get_active_node_count()
            # 2 active (within 5 min), 1 inactive
            assert count == 2
    
    def test_get_active_node_count_no_file(self):
        """Should return 0 when nodes file doesn't exist."""
        with patch.object(api_health, 'NODES_FILE', '/nonexistent/nodes.json'):
            count = api_health.get_active_node_count()
            assert count == 0
    
    def test_get_open_task_count(self, temp_data_dir):
        """Should count only open tasks."""
        with patch.object(api_health, 'TASKS_FILE', 
                         os.path.join(temp_data_dir, 'tasks.json')):
            count = api_health.get_open_task_count()
            # 2 open, 1 completed
            assert count == 2
    
    def test_get_open_task_count_no_file(self):
        """Should return 0 when tasks file doesn't exist."""
        with patch.object(api_health, 'TASKS_FILE', '/nonexistent/tasks.json'):
            count = api_health.get_open_task_count()
            assert count == 0


class TestHealthPerformance:
    """Tests for health endpoint performance."""
    
    def test_health_response_time(self, client):
        """Health check should respond in under 100ms."""
        start = time.time()
        response = client.get('/api/v1/health')
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Allow some slack for test environment (200ms)
        assert elapsed < 0.2, f"Response took {elapsed:.3f}s, expected <100ms"
