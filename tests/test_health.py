"""
Tests for the health check API endpoint.
"""

import pytest
import json
import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """Create test client."""
    # Set up test environment
    os.environ['DATA_DIR'] = '/tmp/wattcoin_test_data'
    os.environ['NODES_FILE'] = '/tmp/wattcoin_test_data/nodes.json'
    os.environ['TASKS_FILE'] = '/tmp/wattcoin_test_data/tasks.json'
    
    # Create test data directory
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    from bridge_web import app
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client
    
    # Cleanup
    import shutil
    if os.path.exists('/tmp/wattcoin_test_data'):
        shutil.rmtree('/tmp/wattcoin_test_data')


def test_health_endpoint_returns_200(client):
    """Test that health endpoint returns 200 when healthy."""
    # Create valid test data files
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump({'nodes': {}}, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump({'tasks': []}, f)
    
    response = client.get('/api/v1/health')
    assert response.status_code == 200


def test_health_endpoint_response_format(client):
    """Test that health endpoint returns correct JSON format."""
    # Create valid test data files
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump({'nodes': {}}, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump({'tasks': []}, f)
    
    response = client.get('/api/v1/health')
    data = json.loads(response.data)
    
    # Check required fields
    assert 'status' in data
    assert 'version' in data
    assert 'uptime_seconds' in data
    assert 'services' in data
    assert 'active_nodes' in data
    assert 'open_tasks' in data
    assert 'timestamp' in data
    
    # Check services subfields
    assert 'database' in data['services']
    assert 'discord' in data['services']
    assert 'ai_api' in data['services']


def test_health_endpoint_counts_active_nodes(client):
    """Test that health endpoint correctly counts active nodes."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    # Create nodes with recent heartbeats (active)
    current_time = time.time()
    nodes_data = {
        'nodes': {
            'node1': {'last_heartbeat': current_time - 10},  # 10 seconds ago - active
            'node2': {'last_heartbeat': current_time - 60},  # 1 minute ago - active
            'node3': {'last_heartbeat': current_time - 300}  # 5 minutes ago - inactive
        }
    }
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump(nodes_data, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump({'tasks': []}, f)
    
    response = client.get('/api/v1/health')
    data = json.loads(response.data)
    
    # Should count 2 active nodes (heartbeat within 120 seconds)
    assert data['active_nodes'] == 2


def test_health_endpoint_counts_open_tasks(client):
    """Test that health endpoint correctly counts open tasks."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    tasks_data = {
        'tasks': [
            {'id': '1', 'status': 'open'},
            {'id': '2', 'status': 'open'},
            {'id': '3', 'status': 'completed'},
            {'id': '4', 'status': 'claimed'}
        ]
    }
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump({'nodes': {}}, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump(tasks_data, f)
    
    response = client.get('/api/v1/health')
    data = json.loads(response.data)
    
    # Should count 2 open tasks
    assert data['open_tasks'] == 2


def test_health_endpoint_no_auth_required(client):
    """Test that health endpoint works without authentication."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump({'nodes': {}}, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump({'tasks': []}, f)
    
    # No auth headers
    response = client.get('/api/v1/health')
    
    # Should still succeed
    assert response.status_code in [200, 503]


def test_health_endpoint_uptime_increases(client):
    """Test that uptime_seconds is a positive integer."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump({'nodes': {}}, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump({'tasks': []}, f)
    
    response = client.get('/api/v1/health')
    data = json.loads(response.data)
    
    assert isinstance(data['uptime_seconds'], int)
    assert data['uptime_seconds'] >= 0


def test_health_endpoint_timestamp_format(client):
    """Test that timestamp is in ISO format."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    with open('/tmp/wattcoin_test_data/nodes.json', 'w') as f:
        json.dump({'nodes': {}}, f)
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump({'tasks': []}, f)
    
    response = client.get('/api/v1/health')
    data = json.loads(response.data)
    
    # Should be parseable as ISO timestamp
    from datetime import datetime
    try:
        # Python 3.11+ supports 'Z' suffix, earlier versions need to handle it
        ts = data['timestamp'].replace('Z', '+00:00')
        datetime.fromisoformat(ts)
    except ValueError:
        pytest.fail(f"Timestamp '{data['timestamp']}' is not valid ISO format")
