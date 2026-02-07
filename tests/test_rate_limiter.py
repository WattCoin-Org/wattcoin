"""
Tests for the enhanced rate limiter middleware.
"""

import pytest
import json
import os
import sys
import time
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rate_limiter import (
    get_wallet_from_request,
    check_wallet_stake,
    get_rate_limit_for_wallet,
    add_rate_limit_headers,
    check_rate_limit,
    cleanup_expired_buckets,
    DEFAULT_RATE_LIMIT,
    AUTHENTICATED_RATE_LIMIT,
    STAKED_RATE_LIMIT,
    _rate_buckets
)


class TestGetWalletFromRequest:
    """Tests for wallet extraction from request."""
    
    def test_wallet_from_authorization_header(self):
        """Test extracting wallet from Authorization header."""
        with patch('rate_limiter.request') as mock_request:
            mock_request.headers = {'Authorization': 'Wallet ABC123'}
            mock_request.get_json.return_value = None
            
            result = get_wallet_from_request()
            assert result == 'ABC123'
    
    def test_wallet_from_x_wallet_header(self):
        """Test extracting wallet from X-Wallet header."""
        with patch('rate_limiter.request') as mock_request:
            mock_request.headers = {'X-Wallet': 'DEF456'}
            mock_request.get_json.return_value = None
            
            result = get_wallet_from_request()
            assert result == 'DEF456'
    
    def test_wallet_from_body(self):
        """Test extracting wallet from request body."""
        with patch('rate_limiter.request') as mock_request:
            mock_request.headers = {}
            mock_request.get_json.return_value = {'wallet': 'GHI789'}
            
            result = get_wallet_from_request()
            assert result == 'GHI789'
    
    def test_no_wallet(self):
        """Test when no wallet is provided."""
        with patch('rate_limiter.request') as mock_request:
            mock_request.headers = {}
            mock_request.get_json.return_value = {}
            
            result = get_wallet_from_request()
            assert result is None


class TestGetRateLimitForWallet:
    """Tests for tier-based rate limits."""
    
    def test_public_rate_limit(self):
        """Test rate limit for unauthenticated requests."""
        limit, tier = get_rate_limit_for_wallet(None)
        assert limit == DEFAULT_RATE_LIMIT
        assert tier == "public"
    
    @patch('rate_limiter.check_wallet_stake')
    def test_authenticated_rate_limit(self, mock_stake):
        """Test rate limit for authenticated wallets without stake."""
        mock_stake.return_value = 0
        
        limit, tier = get_rate_limit_for_wallet("SomeWallet123")
        assert limit == AUTHENTICATED_RATE_LIMIT
        assert tier == "authenticated"
    
    @patch('rate_limiter.check_wallet_stake')
    def test_staked_rate_limit(self, mock_stake):
        """Test rate limit for staked wallets."""
        mock_stake.return_value = 15000  # Above MIN_STAKE_FOR_BOOST
        
        limit, tier = get_rate_limit_for_wallet("StakedWallet")
        assert limit == STAKED_RATE_LIMIT
        assert tier == "staked"


class TestCheckRateLimit:
    """Tests for rate limit checking."""
    
    def setup_method(self):
        """Clear rate buckets before each test."""
        _rate_buckets.clear()
    
    def test_first_request_allowed(self):
        """Test that first request is always allowed."""
        allowed, remaining, reset_time, retry_after = check_rate_limit("test_id", 60)
        
        assert allowed is True
        assert remaining == 59
        assert retry_after == 0
    
    def test_limit_exhaustion(self):
        """Test that requests are blocked when limit is exhausted."""
        limit = 5
        
        # Make limit requests
        for i in range(limit):
            allowed, remaining, _, _ = check_rate_limit("exhaust_test", limit)
            assert allowed is True
            assert remaining == limit - i - 1
        
        # Next request should be blocked
        allowed, remaining, reset_time, retry_after = check_rate_limit("exhaust_test", limit)
        assert allowed is False
        assert remaining == 0
        assert retry_after > 0
    
    def test_different_identifiers(self):
        """Test that different identifiers have separate limits."""
        allowed1, remaining1, _, _ = check_rate_limit("user_a", 10)
        allowed2, remaining2, _, _ = check_rate_limit("user_b", 10)
        
        assert allowed1 is True
        assert allowed2 is True
        assert remaining1 == 9
        assert remaining2 == 9


class TestRateLimitHeaders:
    """Tests for rate limit response headers."""
    
    def test_headers_added(self):
        """Test that rate limit headers are added to response."""
        mock_response = MagicMock()
        mock_response.headers = {}
        
        result = add_rate_limit_headers(mock_response, 60, 45, 1707300000)
        
        assert result.headers['X-RateLimit-Limit'] == '60'
        assert result.headers['X-RateLimit-Remaining'] == '45'
        assert result.headers['X-RateLimit-Reset'] == '1707300000'
    
    def test_remaining_not_negative(self):
        """Test that remaining is never negative."""
        mock_response = MagicMock()
        mock_response.headers = {}
        
        add_rate_limit_headers(mock_response, 60, -5, 1707300000)
        
        assert mock_response.headers['X-RateLimit-Remaining'] == '0'


class TestCleanupExpiredBuckets:
    """Tests for bucket cleanup."""
    
    def test_cleanup_removes_old_buckets(self):
        """Test that old buckets are cleaned up."""
        _rate_buckets.clear()
        
        # Add an expired bucket
        _rate_buckets["old_bucket"] = {
            "window_start": time.time() - 300,  # 5 minutes ago
            "count": 50
        }
        
        # Add a current bucket
        current_window = int(time.time() / 60) * 60
        _rate_buckets["current_bucket"] = {
            "window_start": current_window,
            "count": 10
        }
        
        cleanup_expired_buckets()
        
        assert "old_bucket" not in _rate_buckets
        assert "current_bucket" in _rate_buckets


class TestEnvironmentVariables:
    """Tests for environment variable configuration."""
    
    def test_default_values(self):
        """Test default configuration values."""
        assert DEFAULT_RATE_LIMIT == int(os.getenv('RATE_LIMIT_DEFAULT', 60))
        assert AUTHENTICATED_RATE_LIMIT == int(os.getenv('RATE_LIMIT_AUTHENTICATED', 200))
        assert STAKED_RATE_LIMIT == int(os.getenv('RATE_LIMIT_STAKED', 500))


@pytest.fixture
def client():
    """Create test client with rate limiter middleware."""
    os.environ['DATA_DIR'] = '/tmp/wattcoin_test_data'
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    from flask import Flask
    from rate_limiter import rate_limit_middleware, rate_limit_after_request
    
    app = Flask(__name__)
    app.before_request(rate_limit_middleware)
    app.after_request(rate_limit_after_request)
    
    @app.route('/api/v1/test')
    def test_endpoint():
        return {"success": True}
    
    @app.route('/api/v1/health')
    def health():
        return {"status": "healthy"}
    
    app.config['TESTING'] = True
    
    _rate_buckets.clear()
    
    with app.test_client() as client:
        yield client
    
    import shutil
    if os.path.exists('/tmp/wattcoin_test_data'):
        shutil.rmtree('/tmp/wattcoin_test_data')


def test_middleware_adds_headers(client):
    """Test that middleware adds rate limit headers."""
    response = client.get('/api/v1/test')
    
    assert 'X-RateLimit-Limit' in response.headers
    assert 'X-RateLimit-Remaining' in response.headers
    assert 'X-RateLimit-Reset' in response.headers


def test_middleware_skips_health(client):
    """Test that health endpoint is not rate limited."""
    # Make many requests to health endpoint
    for _ in range(100):
        response = client.get('/api/v1/health')
        assert response.status_code == 200


def test_middleware_returns_429(client):
    """Test that 429 is returned when limit exceeded."""
    _rate_buckets.clear()
    
    # Exhaust the limit (default 60)
    for i in range(60):
        response = client.get('/api/v1/test')
        assert response.status_code == 200
    
    # Next request should be 429
    response = client.get('/api/v1/test')
    assert response.status_code == 429
    assert 'Retry-After' in response.headers
    
    data = json.loads(response.data)
    assert data['error'] == 'rate_limit_exceeded'
    assert 'retry_after_seconds' in data


def test_authenticated_gets_higher_limit(client):
    """Test that authenticated requests get higher limits."""
    _rate_buckets.clear()
    
    # Make requests with wallet header
    for i in range(65):  # More than public limit (60)
        response = client.get(
            '/api/v1/test',
            headers={'X-Wallet': 'TestWallet123'}
        )
        # Authenticated limit is 200, so should still be allowed
        assert response.status_code == 200
