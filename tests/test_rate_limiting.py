"""Tests for API rate limiting on public endpoints (#88)."""
import os
import pytest


@pytest.fixture
def client():
    """Create test client with tight rate limit for testing."""
    os.environ["RATE_LIMIT_PUBLIC"] = "2 per minute"
    # Import after setting env so the limit is picked up
    from bridge_web import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_rate_limit_headers_present(client):
    """Public endpoints should include X-RateLimit-* headers."""
    resp = client.get("/health")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
    assert "X-RateLimit-Reset" in resp.headers


def test_rate_limit_headers_on_pricing(client):
    """Pricing endpoint should include rate limit headers."""
    resp = client.get("/api/v1/pricing")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


def test_rate_limit_headers_on_bounty_stats(client):
    """Bounty stats endpoint should include rate limit headers."""
    resp = client.get("/api/v1/bounty-stats")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


def test_429_includes_retry_after(client):
    """Exceeding rate limit returns 429 with Retry-After header."""
    # Exhaust the limit (set to 2/min in fixture)
    for _ in range(3):
        resp = client.get("/health")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    # Verify Retry-After is a valid number (dynamic from Flask-Limiter)
    retry_after = resp.headers.get("Retry-After")
    assert retry_after.isdigit(), "Retry-After should be numeric"
    data = resp.get_json()
    assert data["error"] == "Rate limit exceeded"
    assert "seconds" in data["retry_after"]
