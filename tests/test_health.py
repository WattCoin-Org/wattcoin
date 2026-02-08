"""Tests for the extended /health endpoint."""
import json
import pytest
from unittest.mock import patch, mock_open


class TestHealthEndpoint:
    """Test suite for /health endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from bridge_web import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_health_returns_200_when_healthy(self, client, monkeypatch):
        """Health returns 200 when all services are ok."""
        monkeypatch.setenv('AI_API_KEY', 'test-key')
        monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/webhook')
        
        with patch('bridge_web.os.path.isfile', return_value=True), \
             patch('bridge_web.os.access', return_value=True), \
             patch('bridge_web.get_active_nodes', return_value=[]):
            response = client.get('/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert 'uptime_seconds' in data
        assert 'services' in data
        assert 'timestamp' in data

    def test_health_returns_503_when_database_degraded(self, client, monkeypatch):
        """Health returns 503 when database is not accessible."""
        monkeypatch.setenv('AI_API_KEY', 'test-key')
        
        with patch('bridge_web.os.path.isfile', return_value=False), \
             patch('bridge_web.get_active_nodes', return_value=[]):
            response = client.get('/health')
        
        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['status'] == 'degraded'
        assert data['services']['database'] == 'degraded'

    def test_health_returns_503_when_ai_api_missing(self, client, monkeypatch):
        """Health returns 503 when AI API keys are missing."""
        monkeypatch.delenv('AI_API_KEY', raising=False)
        monkeypatch.delenv('CLAUDE_API_KEY', raising=False)
        
        with patch('bridge_web.os.path.isfile', return_value=True), \
             patch('bridge_web.os.access', return_value=True), \
             patch('bridge_web.get_active_nodes', return_value=[]):
            response = client.get('/health')
        
        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['services']['ai_api'] == 'degraded'

    def test_health_includes_node_and_task_counts(self, client, monkeypatch):
        """Health includes active_nodes and open_tasks counts."""
        monkeypatch.setenv('AI_API_KEY', 'test-key')
        
        mock_nodes = [{'id': 1}, {'id': 2}]
        tasks_data = {'tasks': [
            {'status': 'open'}, 
            {'status': 'completed'},
            {'status': 'open'}
        ]}
        
        with patch('bridge_web.os.path.isfile', return_value=True), \
             patch('bridge_web.os.access', return_value=True), \
             patch('bridge_web.get_active_nodes', return_value=mock_nodes), \
             patch('builtins.open', mock_open(read_data=json.dumps(tasks_data))):
            response = client.get('/health')
        
        data = json.loads(response.data)
        assert data['active_nodes'] == 2
        assert data['open_tasks'] == 2
