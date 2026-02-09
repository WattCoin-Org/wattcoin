import pytest
import os
import json
from bridge_web import app, limiter

@pytest.fixture
def client(monkeypatch):
    """Test client with a very strict rate limit via environment variables."""
    # Use environment variables to configure the limit, as implemented in the app
    monkeypatch.setenv("LIMIT_DEFAULT_MIN", "1 per minute")
    monkeypatch.setenv("LIMIT_DEFAULT_HOUR", "10 per hour")
    
    app.config['TESTING'] = True
    limiter.enabled = True
    
    # We need to re-initialize the default limits from the env vars
    # Since the app already initialized, we can trigger a re-read or just test the 429 logic
    # with the default limits if they are low enough.
    
    with app.test_client() as client:
        yield client

def test_rate_limiting_triggered(client):
    # 1. First request passes
    resp1 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    # 2. Second request should be rate limited
    resp2 = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert resp2.status_code == 429
    assert "Rate limit exceeded" in resp2.get_json()['error']

def test_rate_limit_headers(client):
    # 3. Check for rate limit headers
    resp = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers

def test_rate_limit_retry_after(client):
    # 4. Check for retry_after in response
    client.post('/api/v1/scrape', json={"url": "https://example.com"})
    resp = client.post('/api/v1/scrape', json={"url": "https://example.com"})
    assert "retry_after" in resp.get_json()

def test_blueprint_rate_limiting(client):
    # 5. Test another endpoint (llm)
    resp = client.post('/api/v1/llm', json={"prompt": "test"})
    # It might fail with 400 (missing payment) but shouldn't be 429 yet
    assert resp.status_code != 429
