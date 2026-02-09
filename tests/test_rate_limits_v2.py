import pytest
import os
from bridge_web import app, limiter

@pytest.fixture
def client(monkeypatch):
    """Test client with a very strict rate limit."""
    # Manually override the limiter's default limits for this test
    # since env vars are already evaluated at import time.
    original_limits = limiter._default_limits
    limiter._default_limits = ["1 per minute"]
    
    app.config['TESTING'] = True
    limiter.enabled = True
    
    with app.test_client() as client:
        yield client
        
    # Restore original limits
    limiter._default_limits = original_limits

def test_rate_limiting_triggered(client):
    """Test that rate limiting returns 429 after exceeding limit."""
    # First request
    resp1 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    # Second request should be rate limited because limit is 1/min
    resp2 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    
    assert resp2.status_code == 429
    data = resp2.get_json()
    assert "Rate limit exceeded" in data['error']
    assert "retry_after" in data
