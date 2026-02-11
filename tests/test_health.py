"""Tests for /health endpoint (Bounty #90)"""
import pytest
import json
import time
import os
from unittest.mock import patch, MagicMock, mock_open
import sys
sys.path.insert(0, '..')


def test_health_returns_200_when_healthy():
    """Test /health returns 200 when all services OK."""
    # Mock environment with all vars set
    env_vars = {
        'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook',
        'AI_API_KEY': 'test-key',
    }
    
    with patch.dict(os.environ, env_vars):
        with patch('os.path.exists', return_value=True):
            with patch('os.access', return_value=True):
                with patch('builtins.open', mock_open(read_data='{"tasks":[]}')):
                    from bridge_web import app, SERVICE_START_TIME
                    
                    with app.test_client() as client:
                        response = client.get('/health')
                        assert response.status_code == 200
                        
                        data = json.loads(response.data)
                        assert data['status'] == 'healthy'
                        assert 'uptime_seconds' in data
                        assert 'database' in data['services']
                        assert data['services']['database'] == 'ok'
                        assert data['services']['discord'] == 'ok'
                        assert data['services']['ai_api'] == 'ok'
                        assert 'open_tasks' in data


def test_health_returns_503_when_services_degraded():
    """Test /health returns 503 when services degraded."""
    # No env vars set - all should be degraded
    with patch.dict(os.environ, {}, clear=True):
        with patch('os.path.exists', return_value=False):
            from bridge_web import app
            
            with app.test_client() as client:
                response = client.get('/health')
                assert response.status_code == 503
                
                data = json.loads(response.data)
                assert data['status'] == 'degraded'
                assert data['services']['database'] == 'degraded'
                assert data['services']['discord'] == 'degraded'
                assert data['services']['ai_api'] == 'degraded'


def test_health_counts_open_tasks():
    """Test /health counts open tasks correctly."""
    tasks_data = {
        "tasks": [
            {"status": "open"},
            {"status": "pending"},
            {"status": "active"},
            {"status": "completed"},
            {"status": "open"}
        ]
    }
    
    with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'x', 'GEMINI_KEY': 'x'}):
        with patch('os.path.exists', return_value=True):
            with patch('os.access', return_value=True):
                with patch('builtins.open', mock_open(read_data=json.dumps(tasks_data))):
                    from bridge_web import app
                    
                    with app.test_client() as client:
                        response = client.get('/health')
                        data = json.loads(response.data)
                        assert data['open_tasks'] == 3  # open, pending, active


def test_health_has_uptime_tracking():
    """Test /health includes uptime_seconds."""
    from bridge_web import app, SERVICE_START_TIME
    
    time.sleep(0.1)  # Small delay
    
    with app.test_client() as client:
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'uptime_seconds' in data
        assert data['uptime_seconds'] >= 0
