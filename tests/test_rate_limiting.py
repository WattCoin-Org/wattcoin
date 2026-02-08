"""Tests for rate limiting on public API endpoints (issue #88)."""
import bridge_web


def test_health_returns_rate_limit_headers():
    """Verify X-RateLimit-* headers are present on /health."""
    client = bridge_web.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_pricing_returns_rate_limit_headers():
    """Verify X-RateLimit-* headers are present on /api/v1/pricing."""
    client = bridge_web.app.test_client()
    response = client.get("/api/v1/pricing")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers


def test_rate_limit_429_has_retry_after():
    """Verify 429 response includes Retry-After header."""
    client = bridge_web.app.test_client()
    # Hit /health many times to trigger the rate limit (120/min)
    # Use a low-limit endpoint instead: create a tight limit scenario
    # We test the error handler format directly
    with bridge_web.app.test_request_context():
        from werkzeug.exceptions import TooManyRequests
        err = TooManyRequests()
        response = bridge_web.ratelimit_handler(err)
        # ratelimit_handler returns a Response object
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        data = response.get_json()
        assert data["error"] == "Rate limit exceeded"
        assert "retry_after" in data


def test_rate_limit_env_vars_loaded():
    """Verify env var defaults are applied."""
    assert bridge_web.RATE_LIMIT_DEFAULT == "60 per minute"
    assert bridge_web.RATE_LIMIT_HOURLY == "1000 per hour"
