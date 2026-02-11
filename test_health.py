"""Tests for health_endpoint.py (Bounty #90)"""
import pytest
import json
import os
from unittest.mock import patch, mock_open
import sys
sys.path.insert(0, '.')
from health_endpoint import get_service_status, get_uptime, get_open_tasks, extended_health_check


def test_get_service_status():
    """Test service status detection."""
    with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://test.webhook', 'AI_API_KEY': 'test'}):
        with patch('os.path.exists', return_value=True):
            with patch('os.access', return_value=True):
                status = get_service_status()
                assert status['database'] == 'ok'
                assert status['discord'] == 'ok'
                assert status['ai_api'] == 'ok'


def test_get_service_status_degraded():
    """Test degraded service status."""
    with patch.dict(os.environ, {}, clear=True):
        with patch('os.path.exists', return_value=False):
            status = get_service_status()
            assert status['database'] == 'degraded'
            assert status['discord'] == 'degraded'
            assert status['ai_api'] == 'degraded'


def test_get_uptime():
    """Test uptime returns positive number."""
    uptime = get_uptime()
    assert uptime >= 0


def test_get_open_tasks():
    """Test open tasks counting."""
    tasks_data = {
        "tasks": [
            {"status": "open"},
            {"status": "completed"},
            {"status": "pending"},
            {"status": "open"}
        ]
    }
    
    with patch('os.path.exists', return_value=True):
        with patch('os.access', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(tasks_data))):
                count = get_open_tasks()
                assert count == 2  # open + pending


def test_extended_health_check():
    """Test full health check returns correct structure."""
    mock_get_active_nodes = lambda: ['node1', 'node2']
    
    with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'test', 'AI_API_KEY': 'test'}):
        with patch('os.path.exists', return_value=True):
            with patch('os.access', return_value=True):
                response, code = extended_health_check(None, None, mock_get_active_nodes)
                
                assert code == 200  # Healthy
                assert response['status'] == 'healthy'
                assert 'uptime_seconds' in response
                assert 'services' in response
                assert response['active_nodes'] == 2
                assert response['services']['database'] == 'ok'


def test_extended_health_check_degraded():
    """Test degraded health check."""
    with patch.dict(os.environ, {}, clear=True):
        with patch('os.path.exists', return_value=False):
            response, code = extended_health_check(None, None, list)
            
            assert code == 503  # Degraded
            assert response['status'] == 'degraded'
