"""Test health endpoint (Bounty #90)"""
import pytest
import json
import os
from unittest.mock import patch, mock_open

def test_health_returns_200_when_healthy(client):
    """Test healthy response when all services OK."""
    with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.webhook', 'AI_API_KEY': 'test'}):
        with patch('os.path.exists', return_value=True):
            with patch('os.access', return_value=True):
                with patch('builtins.open', mock_open(read_data='{"tasks":[]}')):
                    from bridge_web import app
                    with app.test_client() as c:
                        resp = c.get('/health')
                        assert resp.status_code == 200
                        data = json.loads(resp.data)
                        assert data['status'] == 'healthy'
                        assert 'uptime_seconds' in data
                        assert data['services']['database'] == 'ok'

def test_health_returns_503_when_degraded(client):
    """Test degraded response when services down."""
    with patch.dict(os.environ, {}, clear=True):
        with patch('os.path.exists', return_value=False):
            from bridge_web import app
            with app.test_client() as c:
                resp = c.get('/health')
                assert resp.status_code == 503
                data = json.loads(resp.data)
                assert data['status'] == 'degraded'
