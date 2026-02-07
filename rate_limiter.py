"""
Enhanced Rate Limiting Middleware for WattCoin API
v1.0.0 - Implements bounty issue #88

Features:
- Default 60 requests/minute per IP for public endpoints
- Higher limits for authenticated/staked wallets
- Rate limit headers in responses (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
- 429 Too Many Requests response with Retry-After header
- Configurable via environment variables
"""

import os
import time
import logging
from functools import wraps
from flask import request, jsonify, g, make_response

logger = logging.getLogger(__name__)

# === Configuration from Environment Variables ===
DEFAULT_RATE_LIMIT = int(os.getenv('RATE_LIMIT_DEFAULT', 60))  # requests per minute
AUTHENTICATED_RATE_LIMIT = int(os.getenv('RATE_LIMIT_AUTHENTICATED', 200))  # requests per minute
STAKED_RATE_LIMIT = int(os.getenv('RATE_LIMIT_STAKED', 500))  # requests per minute
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', 60))  # seconds

# Minimum stake to qualify for higher limits (in WATT)
MIN_STAKE_FOR_BOOST = int(os.getenv('RATE_LIMIT_MIN_STAKE', 10000))


def get_wallet_from_request():
    """
    Extract wallet address from request.
    Checks Authorization header, X-Wallet header, and request body.
    """
    # Check Authorization header
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Wallet '):
        return auth[7:].strip()
    
    # Check X-Wallet header
    wallet_header = request.headers.get('X-Wallet', '')
    if wallet_header:
        return wallet_header.strip()
    
    # Check request body
    body = request.get_json(silent=True) or {}
    wallet = body.get('wallet', '')
    if wallet:
        return wallet.strip()
    
    return None


def check_wallet_stake(wallet):
    """
    Check if wallet has enough stake for boosted rate limits.
    Returns stake amount in WATT.
    """
    if not wallet:
        return 0
    
    try:
        # Import from api_nodes to check stake
        from api_nodes import load_nodes
        nodes_data = load_nodes()
        
        # Check if wallet is a registered node with stake
        for node_id, node in nodes_data.get('nodes', {}).items():
            if node.get('wallet') == wallet:
                return node.get('stake', 0)
        
        return 0
    except Exception as e:
        logger.debug("Could not check wallet stake: %s", e)
        return 0


def get_rate_limit_for_wallet(wallet):
    """
    Get appropriate rate limit based on wallet authentication and stake.
    
    Returns:
        Tuple of (limit, tier_name)
    """
    if not wallet:
        return DEFAULT_RATE_LIMIT, "public"
    
    stake = check_wallet_stake(wallet)
    
    if stake >= MIN_STAKE_FOR_BOOST:
        return STAKED_RATE_LIMIT, "staked"
    else:
        return AUTHENTICATED_RATE_LIMIT, "authenticated"


def add_rate_limit_headers(response, limit, remaining, reset_time):
    """
    Add rate limit headers to response.
    
    Headers:
    - X-RateLimit-Limit: Maximum requests allowed in window
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Unix timestamp when window resets
    """
    response.headers['X-RateLimit-Limit'] = str(limit)
    response.headers['X-RateLimit-Remaining'] = str(max(0, remaining))
    response.headers['X-RateLimit-Reset'] = str(int(reset_time))
    return response


def create_429_response(retry_after, limit):
    """
    Create a properly formatted 429 Too Many Requests response.
    """
    response = make_response(jsonify({
        "success": False,
        "error": "rate_limit_exceeded",
        "message": "Too many requests. Please slow down and try again later.",
        "retry_after_seconds": retry_after,
        "limit": limit,
        "window_seconds": RATE_LIMIT_WINDOW
    }), 429)
    
    response.headers['Retry-After'] = str(retry_after)
    response.headers['X-RateLimit-Limit'] = str(limit)
    response.headers['X-RateLimit-Remaining'] = '0'
    response.headers['X-RateLimit-Reset'] = str(int(time.time() + retry_after))
    
    return response


# === In-Memory Rate Limit Storage ===
# For production, use Redis via Flask-Limiter's storage_uri
_rate_buckets = {}


def get_bucket_key(identifier, endpoint=None):
    """Generate unique key for rate limit bucket."""
    if endpoint:
        return f"{identifier}:{endpoint}"
    return identifier


def check_rate_limit(identifier, limit):
    """
    Check and update rate limit for an identifier.
    
    Returns:
        Tuple of (allowed, remaining, reset_time, retry_after)
    """
    current_time = time.time()
    window_start = int(current_time / RATE_LIMIT_WINDOW) * RATE_LIMIT_WINDOW
    window_end = window_start + RATE_LIMIT_WINDOW
    
    bucket_key = get_bucket_key(identifier)
    
    # Get or create bucket
    if bucket_key not in _rate_buckets:
        _rate_buckets[bucket_key] = {
            "window_start": window_start,
            "count": 0
        }
    
    bucket = _rate_buckets[bucket_key]
    
    # Reset bucket if window has passed
    if bucket["window_start"] < window_start:
        bucket["window_start"] = window_start
        bucket["count"] = 0
    
    # Check if limit exceeded
    if bucket["count"] >= limit:
        retry_after = int(window_end - current_time)
        return False, 0, window_end, max(1, retry_after)
    
    # Increment counter
    bucket["count"] += 1
    remaining = limit - bucket["count"]
    
    return True, remaining, window_end, 0


def rate_limit_middleware():
    """
    Flask before_request handler for rate limiting.
    
    To enable, add to your Flask app:
        from rate_limiter import rate_limit_middleware
        app.before_request(rate_limit_middleware)
    """
    # Skip rate limiting for health checks and static files
    if request.path in ('/api/v1/health', '/health', '/favicon.ico'):
        return None
    
    # Skip for internal/admin routes
    if request.path.startswith('/admin'):
        return None
    
    # Get identifier (wallet or IP)
    wallet = get_wallet_from_request()
    if wallet:
        identifier = f"wallet:{wallet}"
    else:
        identifier = f"ip:{request.remote_addr}"
    
    # Get appropriate rate limit
    limit, tier = get_rate_limit_for_wallet(wallet)
    
    # Check rate limit
    allowed, remaining, reset_time, retry_after = check_rate_limit(identifier, limit)
    
    # Store for after_request handler
    g.rate_limit_info = {
        "limit": limit,
        "remaining": remaining,
        "reset_time": reset_time,
        "tier": tier
    }
    
    if not allowed:
        logger.warning(
            "Rate limit exceeded | identifier=%s tier=%s limit=%d path=%s",
            identifier[:20], tier, limit, request.path
        )
        return create_429_response(retry_after, limit)
    
    return None


def rate_limit_after_request(response):
    """
    Flask after_request handler to add rate limit headers.
    
    To enable, add to your Flask app:
        from rate_limiter import rate_limit_after_request
        app.after_request(rate_limit_after_request)
    """
    info = getattr(g, 'rate_limit_info', None)
    if info:
        add_rate_limit_headers(
            response,
            info["limit"],
            info["remaining"],
            info["reset_time"]
        )
    return response


def rate_limit(limit=None, per_minute=True):
    """
    Decorator for custom rate limiting on specific endpoints.
    
    Usage:
        @app.route('/api/expensive')
        @rate_limit(limit=10)
        def expensive_endpoint():
            ...
    
    Args:
        limit: Max requests allowed (default: use tier-based limit)
        per_minute: If True, limit is per minute (default: True)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            wallet = get_wallet_from_request()
            
            if limit:
                effective_limit = limit
                tier = "custom"
            else:
                effective_limit, tier = get_rate_limit_for_wallet(wallet)
            
            if wallet:
                identifier = f"wallet:{wallet}:{request.endpoint}"
            else:
                identifier = f"ip:{request.remote_addr}:{request.endpoint}"
            
            allowed, remaining, reset_time, retry_after = check_rate_limit(
                identifier, effective_limit
            )
            
            if not allowed:
                logger.warning(
                    "Rate limit exceeded (decorator) | endpoint=%s tier=%s limit=%d",
                    request.endpoint, tier, effective_limit
                )
                return create_429_response(retry_after, effective_limit)
            
            response = make_response(f(*args, **kwargs))
            add_rate_limit_headers(response, effective_limit, remaining, reset_time)
            return response
        
        return decorated_function
    return decorator


# === Cleanup Task ===
def cleanup_expired_buckets():
    """
    Remove expired rate limit buckets to prevent memory growth.
    Call periodically (e.g., every 5 minutes).
    """
    current_time = time.time()
    window_start = int(current_time / RATE_LIMIT_WINDOW) * RATE_LIMIT_WINDOW
    
    expired_keys = [
        key for key, bucket in _rate_buckets.items()
        if bucket["window_start"] < window_start - RATE_LIMIT_WINDOW
    ]
    
    for key in expired_keys:
        del _rate_buckets[key]
    
    if expired_keys:
        logger.debug("Cleaned up %d expired rate limit buckets", len(expired_keys))
