import pytest
import time
from bridge_web import app
from extensions import limiter
from config_rates import RateLimitConfig

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Reset limits for clean testing
    limiter.reset()
    with app.test_client() as client:
        yield client

def test_scrape_rate_limit(client):
    """Verify scrape endpoint is rate limited (10/min)"""
    url = "/api/v1/scrape"
    payload = {
        "url": "https://example.com", 
        "format": "text",
        "wallet": "TestWallet",
        "tx_signature": "TestSig"
    }
    
    # Send 10 allowed requests
    for i in range(10):
        # We might get 400 (payment error) but that still counts towards rate limit
        resp = client.post(url, json=payload)
        # 400 means it passed rate limit, 429 means blocked
        assert resp.status_code != 429, f"Request {i+1} blocked prematurely"

    # 11th request should be blocked
    resp = client.post(url, json=payload)
    assert resp.status_code == 429, "Rate limit not enforced on 11th request"
    assert "429" in resp.status, "Response should be 429 Too Many Requests"

def test_register_node_rate_limit(client):
    """Verify register node endpoint is strictly rate limited (5/hour)"""
    url = "/api/v1/nodes/register"
    payload = {
        "wallet": "TestNodeWallet",
        "stake_tx": "TestStakeSig",
        "capabilities": ["scrape"]
    }
    
    # Send 5 allowed requests
    for i in range(5):
        resp = client.post(url, json=payload)
        assert resp.status_code != 429, f"Request {i+1} blocked prematurely"
        
    # 6th request should be blocked
    resp = client.post(url, json=payload)
    assert resp.status_code == 429, "Rate limit not enforced on 6th request"
