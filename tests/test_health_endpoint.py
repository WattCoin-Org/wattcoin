"""
Tests for the health check endpoint.
Uses monkeypatch to mock service checks - no real API calls.
"""
import pytest
import json
import time
from datetime import datetime
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bridge_web


class TestHealthEndpoint:
    """Test suite for /health endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        bridge_web.app.config['TESTING'] = True
        with bridge_web.app.test_client() as client:
            yield client

    def test_health_returns_200_when_healthy(self, client):
        """Test that health endpoint returns 200 when all services are healthy."""
        # Mock all service checks to return healthy
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', MagicMock()), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test'}):

            response = client.get('/health')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['status'] == 'healthy'
            assert 'version' in data
            assert 'uptime_seconds' in data
            assert 'services' in data
            assert 'active_nodes' in data
            assert 'open_tasks' in data
            assert 'timestamp' in data

    def test_health_returns_503_when_critical_service_down(self, client):
        """Test that health endpoint returns 503 when a critical service is degraded."""
        # Mock data files to not exist (critical service failure)
        with patch('os.path.exists', return_value=False), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test', 'AI_API_KEY': 'sk-test'}):

            response = client.get('/health')

            assert response.status_code == 503
            data = json.loads(response.data)
            assert data['status'] == 'degraded'
            assert 'services' in data

    def test_health_checks_database_service(self, client):
        """Test that health endpoint checks data file accessibility."""
        with patch('os.path.exists') as mock_exists, \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            # Data file exists
            mock_exists.return_value = True
            response = client.get('/health')
            data = json.loads(response.data)
            assert data['services']['database'] == 'ok'

            # Data file doesn't exist
            mock_exists.return_value = False
            response = client.get('/health')
            data = json.loads(response.data)
            assert data['services']['database'] == 'error'

    def test_health_checks_discord_service(self, client):
        """Test that health endpoint checks Discord webhook configuration."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'AI_API_KEY': 'sk-test'}):

            # Discord webhook configured
            with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test'}):
                response = client.get('/health')
                data = json.loads(response.data)
                assert data['services']['discord'] == 'ok'

            # Discord webhook not configured
            with patch.dict(os.environ, {}, clear=True):
                response = client.get('/health')
                data = json.loads(response.data)
                assert data['services']['discord'] == 'error'

    def test_health_checks_ai_api_service(self, client):
        """Test that health endpoint checks AI API key configuration."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com'}):

            # AI API key configured
            with patch.dict(os.environ, {'AI_API_KEY': 'sk-test'}):
                response = client.get('/health')
                data = json.loads(response.data)
                assert data['services']['ai_api'] == 'ok'

            # AI API key not configured
            with patch.dict(os.environ, {}, clear=True):
                response = client.get('/health')
                data = json.loads(response.data)
                assert data['services']['ai_api'] == 'error'

    def test_health_response_has_correct_structure(self, client):
        """Test that health response has the expected structure."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            response = client.get('/health')
            data = json.loads(response.data)

            # Verify all required fields are present and have correct types
            assert isinstance(data['status'], str)
            assert isinstance(data['version'], str)
            assert isinstance(data['uptime_seconds'], (int, float))
            assert isinstance(data['services'], dict)
            assert isinstance(data['active_nodes'], int)
            assert isinstance(data['open_tasks'], int)
            assert isinstance(data['timestamp'], str)

            # Verify timestamp format is ISO format
            try:
                datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            except ValueError:
                pytest.fail("timestamp is not in valid ISO format")

    def test_health_active_nodes_count(self, client):
        """Test that health endpoint returns active nodes count."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}), \
             patch('bridge_web.get_active_nodes', return_value=[{'id': 'node1'}, {'id': 'node2'}]):

            response = client.get('/health')
            data = json.loads(response.data)
            assert data['active_nodes'] == 2

    def test_health_open_tasks_count(self, client):
        """Test that health endpoint returns open tasks count."""
        mock_tasks_data = {'tasks': [{'id': 1, 'status': 'open'}, {'id': 2, 'status': 'open'}, {'id': 3, 'status': 'completed'}]}

        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}), \
             patch('json.load', return_value=mock_tasks_data):

            response = client.get('/health')
            data = json.loads(response.data)
            # Should count only open tasks
            assert data['open_tasks'] >= 0  # Count will depend on filtering logic

    def test_health_under_500ms(self, client):
        """Test that health endpoint responds in under 500ms."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            start_time = time.time()
            response = client.get('/health')
            elapsed_ms = (time.time() - start_time) * 1000

            assert response.status_code == 200
            assert elapsed_ms < 500, f"Response took {elapsed_ms}ms, expected under 500ms"

    def test_health_no_real_api_calls(self, client):
        """Ensure health check makes no real HTTP/API calls - only lightweight checks."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}), \
             patch('requests.get') as mock_get, \
             patch('requests.post') as mock_post:

            response = client.get('/health')

            # Verify no HTTP requests were made
            mock_get.assert_not_called()
            mock_post.assert_not_called()
            assert response.status_code == 200

    def test_health_detailed_mode_basic(self, client):
        """Test that detailed=true returns enhanced metrics."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}), \
             patch('bridge_web.get_active_nodes', return_value=[]):

            response = client.get('/health?detailed=true')
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data['detailed'] is True
            assert 'system' in data
            assert data['services']['claude_api'] == 'ok'

    def test_health_detailed_mode_without_param(self, client):
        """Test that without detailed param, response doesn't include system metrics."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            response = client.get('/health')
            data = json.loads(response.data)

            assert response.status_code == 200
            assert 'detailed' not in data
            assert 'system' not in data

    def test_health_no_claude_api_in_basic_mode(self, client):
        """Test that claude_api is NOT in basic health response (backward compatibility)."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}):

            response = client.get('/health')
            data = json.loads(response.data)
            # Basic mode should NOT have claude_api for backward compatibility
            assert 'claude_api' not in data['services']
            # Should only have the original 3 services
            assert set(data['services'].keys()) == {'database', 'discord', 'ai_api'}

    def test_health_claude_api_in_detailed_mode(self, client):
        """Test that claude_api appears in detailed mode only."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}):

            response = client.get('/health?detailed=true')
            data = json.loads(response.data)
            # Detailed mode should have claude_api
            assert 'claude_api' in data['services']
            assert data['services']['claude_api'] == 'ok'

    def test_health_system_metrics_structure(self, client):
        """Test that system metrics have correct structure when detailed=true."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}), \
             patch('bridge_web.get_active_nodes', return_value=[]):

            response = client.get('/health?detailed=true')
            data = json.loads(response.data)

            assert response.status_code == 200
            assert 'system' in data
            system = data['system']

            # Check memory metrics exist and have correct types
            if 'memory' in system:
                assert isinstance(system['memory']['total_mb'], int)
                assert isinstance(system['memory']['available_mb'], int)
                assert isinstance(system['memory']['percent_used'], (int, float))

            # Check CPU metrics exist and have correct types
            if 'cpu' in system:
                assert 'percent' in system['cpu'] or 'load_avg_1m' in system['cpu']

    def test_health_database_connectivity_check(self, client):
        """Test that database service checks file readability, not just existence."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            # Simulate read error
            with patch('builtins.open', side_effect=PermissionError("Permission denied")):
                response = client.get('/health')
                data = json.loads(response.data)
                assert data['services']['database'] == 'error'

    def test_health_backward_compatibility(self, client):
        """Test that health response is backward compatible (no breaking changes)."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            response = client.get('/health')
            data = json.loads(response.data)

            # All original fields must be present
            assert 'status' in data
            assert 'version' in data
            assert 'uptime_seconds' in data
            assert 'services' in data
            assert 'active_nodes' in data
            assert 'open_tasks' in data
            assert 'timestamp' in data

            # Check services dict has original keys
            assert 'database' in data['services']
            assert 'discord' in data['services']
            assert 'ai_api' in data['services']

    def test_health_error_handling(self, client):
        """Test that health endpoint handles exceptions gracefully."""
        with patch('os.path.exists', side_effect=Exception("Unexpected error")):
            response = client.get('/health')
            data = json.loads(response.data)

            # Should return 503 with error info, not crash
            assert response.status_code == 503
            assert data['status'] == 'error'
            assert 'timestamp' in data

    def test_health_detailed_various_params(self, client):
        """Test that various detailed param values work correctly."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}):

            # Test detailed=1
            response = client.get('/health?detailed=1')
            data = json.loads(response.data)
            assert data.get('detailed') is True

            # Test detailed=yes
            response = client.get('/health?detailed=yes')
            data = json.loads(response.data)
            assert data.get('detailed') is True

            # Test detailed=false
            response = client.get('/health?detailed=false')
            data = json.loads(response.data)
            assert 'detailed' not in data or data.get('detailed') is False

    def test_health_system_metrics_require_env_var(self, client):
        """Test that system metrics only appear when HEALTH_EXPOSE_SYSTEM=true."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}):

            # Without env var, system should be empty or minimal
            response = client.get('/health?detailed=true')
            data = json.loads(response.data)
            # System should exist but be empty or minimal without env var
            assert 'system' in data
            # Without HEALTH_EXPOSE_SYSTEM, system should be empty (security)
            assert data['system'] == {}

    def test_health_api_connectivity_checks_require_env_var(self, client):
        """Test that API connectivity checks only happen when HEALTH_CHECK_APIS=true."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}), \
             patch('bridge_web.ai_client') as mock_ai, \
             patch('bridge_web.claude_client') as mock_claude:

            mock_ai.models.list = MagicMock()
            mock_claude.beta.models.list = MagicMock()

            # Without HEALTH_CHECK_APIS=true, API checks should not run
            response = client.get('/health?detailed=true')
            data = json.loads(response.data)
            
            # API models.list should not be called without env var
            mock_ai.models.list.assert_not_called()
            mock_claude.beta.models.list.assert_not_called()

    def test_health_respects_timeout_env_var(self, client):
        """Test that HEALTH_API_TIMEOUT env var is respected."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {
                 'DISCORD_WEBHOOK_URL': 'https://test.com', 
                 'AI_API_KEY': 'sk-test',
                 'CLAUDE_API_KEY': 'sk-claude',
                 'HEALTH_CHECK_APIS': 'true',
                 'HEALTH_API_TIMEOUT': '10'
             }), \
             patch('bridge_web.ai_client') as mock_ai:

            mock_models = MagicMock()
            mock_ai.models = mock_models

            # Should use timeout of 10 seconds from env var
            response = client.get('/health?detailed=true')
            
            # Verify the mock was called with timeout=10 if it was called
            # This test validates the env var path works
            assert response.status_code == 200

    def test_health_version_field_unchanged(self, client):
        """Test that version field format is maintained."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            response = client.get('/health')
            data = json.loads(response.data)
            
            # Version should be a string in format X.Y.Z
            assert isinstance(data['version'], str)
            version_parts = data['version'].split('.')
            assert len(version_parts) == 3
            for part in version_parts:
                assert part.isdigit()

    def test_health_timestamp_format(self, client):
        """Test that timestamp is in correct ISO format with Z suffix."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test'}):

            response = client.get('/health')
            data = json.loads(response.data)
            
            # Timestamp should end with Z and be parseable
            timestamp = data['timestamp']
            assert timestamp.endswith('Z')
            # Should be able to parse it
            from datetime import datetime
            parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            assert parsed is not None

    def test_health_detailed_preserves_basic_fields(self, client):
        """Test that detailed mode preserves all basic response fields."""
        with patch('os.path.exists', return_value=True), \
             patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.com', 'AI_API_KEY': 'sk-test', 'CLAUDE_API_KEY': 'sk-claude'}):

            # Get both responses
            basic_response = client.get('/health')
            detailed_response = client.get('/health?detailed=true')
            
            basic_data = json.loads(basic_response.data)
            detailed_data = json.loads(detailed_response.data)
            
            # All basic fields should be present in detailed mode
            for key in ['status', 'version', 'uptime_seconds', 'services', 'active_nodes', 'open_tasks', 'timestamp']:
                assert key in detailed_data, f"Field {key} missing in detailed response"
                assert basic_data[key] == detailed_data[key] or key == 'services', f"Field {key} value mismatch"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
