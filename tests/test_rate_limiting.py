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


def test_429_includes_retry_after(client):
    """Exceeding rate limit returns 429 with Retry-After header."""
    # Exhaust the limit (set to 2/min in fixture)
    for _ in range(3):
        resp = client.get("/health")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    data = resp.get_json()
    assert data["error"] == "Rate limit exceeded"


def test_rate_limit_configurable():
    """RATE_LIMIT_PUBLIC env var should configure the limit."""
    os.environ["RATE_LIMIT_PUBLIC"] = "120 per minute"
    # Re-import to pick up new value
    import importlib
    import bridge_web
    importlib.reload(bridge_web)
    assert bridge_web.PUBLIC_RATE_LIMIT == "120 per minute"
