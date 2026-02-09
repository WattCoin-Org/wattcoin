import pytest
from bridge_web import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    """Verify health endpoint returns correct structure and fields"""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    
    # Check new fields
    assert 'status' in data
    assert 'services' in data
    assert 'uptime_seconds' in data
    assert 'active_nodes' in data
    assert 'open_tasks' in data
    
    # Check backward compatibility fields
    assert 'ai' in data
    assert 'claude' in data
    assert 'proxy' in data
    assert 'admin' in data

def test_rate_limiting_headers(client):
    """Verify rate limit headers are present in response"""
    response = client.get('/health')
    assert 'X-RateLimit-Limit' in response.headers
    assert 'X-RateLimit-Remaining' in response.headers
    assert 'X-RateLimit-Reset' in response.headers

def test_pricing_endpoint_ratelimit(client):
    """Verify pricing endpoint has rate limit applied"""
    response = client.get('/api/v1/pricing')
    assert response.status_code == 200
    assert 'X-RateLimit-Limit' in response.headers
