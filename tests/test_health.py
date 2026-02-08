"""Tests for the /health endpoint."""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create test client."""
    # Mock dependencies before importing app
    with patch.dict('os.environ', {
        'DISCORD_WEBHOOK': 'https://discord.test/webhook',
        'OPENAI_API_KEY': 'test-key'
    }):
        with patch('bridge_web.ai_client', MagicMock()):
            with patch('bridge_web.claude_client', MagicMock()):
                from bridge_web import app
                app.config['TESTING'] = True
                with app.test_client() as client:
                    yield client


def test_health_returns_200_when_healthy(client, tmp_path, monkeypatch):
    """Health endpoint returns 200 when all services are up."""
    # Create mock data file
    data_file = tmp_path / "bounty_reviews.json"
    data_file.write_text('{"reviews": []}')
    
    monkeypatch.setattr('bridge_web.DATA_FILE', str(data_file))
    monkeypatch.setattr('bridge_web.get_active_nodes', lambda: [{'id': 1}])
    
    response = client.get('/health')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert 'uptime_seconds' in data
    assert 'services' in data
    assert data['services']['database'] == 'ok'
    assert 'active_nodes' in data
    assert 'open_tasks' in data
    assert 'timestamp' in data


def test_health_returns_503_when_database_missing(client, monkeypatch):
    """Health endpoint returns 503 when database file is missing."""
    monkeypatch.setattr('bridge_web.DATA_FILE', '/nonexistent/path.json')
    monkeypatch.setattr('bridge_web.get_active_nodes', lambda: [])
    
    response = client.get('/health')
    assert response.status_code == 503
    
    data = json.loads(response.data)
    assert data['status'] == 'degraded'
    assert data['services']['database'] == 'degraded'


def test_health_counts_open_tasks(client, tmp_path, monkeypatch):
    """Health endpoint correctly counts pending tasks."""
    data_file = tmp_path / "bounty_reviews.json"
    data_file.write_text(json.dumps({
        'reviews': [
            {'status': 'pending'},
            {'status': 'pending'},
            {'status': 'completed'}
        ]
    }))
    
    monkeypatch.setattr('bridge_web.DATA_FILE', str(data_file))
    monkeypatch.setattr('bridge_web.get_active_nodes', lambda: [])
    
    response = client.get('/health')
    data = json.loads(response.data)
    assert data['open_tasks'] == 2
