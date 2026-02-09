import pytest
import os
import json
from bridge_web import app, limiter

@pytest.fixture
def client(monkeypatch):
    """Test client with a very strict rate limit."""
    # Force a strict limit for testing purposes by overriding the internal attribute
    # This ensures the test is reliable regardless of environment variable timing
    original_limits = limiter._default_limits
    limiter._default_limits = ["1 per minute"]
    
    app.config['TESTING'] = True
    limiter.enabled = True
    
    with app.test_client() as client:
        yield client
        
    # Restore original limits
    limiter._default_limits = original_limits

def test_rate_limiting_triggered(client):
    # 1. First request passes (or fails with 400, but not 429)
    resp1 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert resp1.status_code != 429
    
    # 2. Second request must be rate limited (429)
    resp2 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert resp2.status_code == 429
    assert "Rate limit exceeded" in resp2.get_json()['error']

def test_rate_limit_headers(client):
    # 3. Check for mandatory rate limit headers
    resp = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers

def test_rate_limit_retry_after(client):
    # 4. Check for retry_after in response body
    client.post('/api/v1/scrape', json={"url": "https://example.com"})
    resp = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert "retry_after" in resp.get_json()

def test_blueprint_isolation(client):
    # 5. Verify that rate limiting on one route doesn't immediately block unrelated blueprints
    # Trigger limit on scrape
    client.post('/api/v1/scrape', json={"url": "https://example.com"})
    client.post('/api/v1/scrape', json={"url": "https://example.com"})
    
    # Check llm endpoint - should not be 429 if below its own limit
    resp = client.post('/api/v1/llm', json={"prompt": "test"})
    assert resp.status_code != 429
