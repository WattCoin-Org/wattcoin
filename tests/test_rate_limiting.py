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
    with bridge_web.app.test_request_context():
        from werkzeug.exceptions import TooManyRequests
        err = TooManyRequests()
        response = bridge_web.ratelimit_handler(err)
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        data = response.get_json()
        assert data["error"] == "Rate limit exceeded"
        assert isinstance(data["retry_after"], int)


def test_rate_limit_env_vars_are_configurable():
    """Verify rate limit defaults are loaded and configurable."""
    assert hasattr(bridge_web, "RATE_LIMIT_DEFAULT")
    assert hasattr(bridge_web, "RATE_LIMIT_HOURLY")
    assert "per minute" in bridge_web.RATE_LIMIT_DEFAULT
    assert "per hour" in bridge_web.RATE_LIMIT_HOURLY
