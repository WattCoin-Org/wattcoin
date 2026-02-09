import pytest
import os
from bridge_web import app, limiter

@pytest.fixture
def client(monkeypatch):
    # Set limits BEFORE importing app or enabling limiter
    monkeypatch.setenv("DEFAULT_LIMIT_MIN", "1 per minute")
    app.config['TESTING'] = True
    limiter.enabled = True
    with app.test_client() as client:
        yield client

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
