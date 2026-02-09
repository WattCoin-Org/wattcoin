import pytest
from bridge_web import app, limiter
import time

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Ensure limiter is enabled for tests
    limiter.enabled = True
    with app.test_client() as client:
        yield client

def test_rate_limiting_public_endpoint(client, monkeypatch):
    """Test that rate limiting returns 429 after exceeding limit."""
    # Set a very low limit for testing
    monkeypatch.setenv("DEFAULT_RATE_LIMIT", "1 per minute")
    
    # First request should pass (or fail with 400 due to missing data, but NOT 429)
    resp1 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert resp1.status_code != 429
    
    # Second request should be rate limited
    resp2 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert resp2.status_code == 429
    assert "Rate limit exceeded" in resp2.get_json()['error']
    assert "Retry-After" in resp2.headers or "retry_after" in resp2.get_json()
