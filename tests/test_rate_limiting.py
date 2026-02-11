"""Tests for rate limiting (Bounty #88)"""
import pytest
import time
from unittest.mock import patch, MagicMock


def test_rate_limit_decorator_exists():
    """Verify @limiter.limit is applied to endpoints."""
    # Read bridge_web.py and check decorators
    with open('bridge_web.py', 'r') as f:
        content = f.read()
    
    # Check PUBLIC_RATE_LIMIT is defined
    assert "PUBLIC_RATE_LIMIT" in content
    
    # Check decorators are applied
    assert "@limiter.limit(PUBLIC_RATE_LIMIT)" in content
    
    protected_endpoints = [
        "def scrape()",
        "def llm_query()",
        "def proxy_request()",
        "def unified_pricing()",
        "def bounty_stats()",
        "def index()",
        "def query()"
    ]
    
    # Count protected endpoints
    limit_decorators = content.count("@limiter.limit(PUBLIC_RATE_LIMIT)")
    assert limit_decorators >= 12, f"Expected >=12 decorators, found {limit_decorators}"


def test_rate_limit_env_var():
    """Verify PUBLIC_RATE_LIMIT environment variable is used."""
    from bridge_web import PUBLIC_RATE_LIMIT
    
    assert PUBLIC_RATE_LIMIT is not None
    assert "minute" in PUBLIC_RATE_LIMIT.lower() or "per" in PUBLIC_RATE_LIMIT.lower()


def test_429_error_handler_exists():
    """Verify 429 error handler exists."""
    with open('bridge_web.py', 'r') as f:
        content = f.read()
    
    assert "@app.errorhandler(429)" in content or "ratelimit_handler" in content


def test_rate_limit_headers_configured():
    """Verify Flask-Limiter headers are enabled."""
    with open('bridge_web.py', 'r') as f:
        content = f.read()
    
    assert "headers_enabled=True" in content or "headers_enabled = True" in content
