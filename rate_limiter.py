"""
Rate Limiter Middleware for WattCoin API
Implements per-IP rate limiting with higher limits for authenticated/staked wallets.

Configuration via environment variables:
- RATE_LIMIT_DEFAULT: requests per minute for public (default: 60)
- RATE_LIMIT_AUTHENTICATED: requests per minute for authenticated (default: 300)
- RATE_LIMIT_STAKED: requests per minute for staked wallets (default: 600)
- RATE_LIMIT_ENABLED: set to "false" to disable (default: true)
"""

import os
import time
import logging
from collections import defaultdict
from functools import wraps
from flask import request, jsonify, g

logger = logging.getLogger(__name__)

# === Configuration ===
RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', 'true').lower() != 'false'
RATE_LIMIT_DEFAULT = int(os.getenv('RATE_LIMIT_DEFAULT', '60'))  # 60/min for public
RATE_LIMIT_AUTHENTICATED = int(os.getenv('RATE_LIMIT_AUTHENTICATED', '300'))  # 300/min for auth
RATE_LIMIT_STAKED = int(os.getenv('RATE_LIMIT_STAKED', '600'))  # 600/min for staked
RATE_LIMIT_WINDOW = 60  # 1 minute window

# In-memory storage for rate limit tracking
# Format: {ip_or_wallet: [(timestamp, count), ...]}
_rate_limit_store = defaultdict(list)


def _get_client_ip():
    """Get client IP, handling proxies."""
    # Check common proxy headers
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr or '127.0.0.1'


def _get_rate_limit_key():
    """Get the rate limit key (wallet if authenticated, else IP)."""
    # Check for wallet in various places
    wallet = None
    
    # From JSON body
    if request.is_json:
        body = request.get_json(silent=True) or {}
        wallet = body.get('wallet')
    
    # From query params
    if not wallet:
        wallet = request.args.get('wallet')
    
    # From headers (for API key auth)
    if not wallet:
        api_key = request.headers.get('X-API-Key')
        if api_key:
            wallet = f"apikey:{api_key[:16]}"
    
    if wallet:
        return f"wallet:{wallet}"
    
    return f"ip:{_get_client_ip()}"


def _get_rate_limit(key):
    """Get the rate limit for a given key."""
    # Staked wallets get highest limit
    if key.startswith('wallet:'):
        wallet = key.replace('wallet:', '')
        if _is_staked_wallet(wallet):
            return RATE_LIMIT_STAKED
        return RATE_LIMIT_AUTHENTICATED
    
    # API key users get authenticated limit
    if 'apikey:' in key:
        return RATE_LIMIT_AUTHENTICATED
    
    # Default public limit
    return RATE_LIMIT_DEFAULT


def _is_staked_wallet(wallet):
    """
    Check if wallet has staked WATT.
    Imports from reputation module if available.
    """
    try:
        from api_reputation import get_reputation
        rep = get_reputation(wallet)
        return rep.get('staked_amount', 0) > 0
    except (ImportError, Exception):
        return False


def _clean_old_entries(key, now):
    """Remove entries older than the rate limit window."""
    window_start = now - RATE_LIMIT_WINDOW
    _rate_limit_store[key] = [
        entry for entry in _rate_limit_store[key]
        if entry[0] > window_start
    ]


def _count_requests(key):
    """Count requests in the current window."""
    now = time.time()
    _clean_old_entries(key, now)
    return sum(entry[1] for entry in _rate_limit_store[key])


def _add_request(key):
    """Record a new request."""
    now = time.time()
    _rate_limit_store[key].append((now, 1))


def check_rate_limit():
    """
    Check rate limit for current request.
    Returns (allowed, limit, remaining, reset_time) tuple.
    """
    if not RATE_LIMIT_ENABLED:
        return True, 0, 0, 0
    
    key = _get_rate_limit_key()
    limit = _get_rate_limit(key)
    current = _count_requests(key)
    remaining = max(0, limit - current)
    
    # Calculate reset time
    now = time.time()
    if _rate_limit_store[key]:
        oldest = min(entry[0] for entry in _rate_limit_store[key])
        reset_time = int(oldest + RATE_LIMIT_WINDOW)
    else:
        reset_time = int(now + RATE_LIMIT_WINDOW)
    
    if current >= limit:
        return False, limit, 0, reset_time
    
    _add_request(key)
    return True, limit, remaining - 1, reset_time


def rate_limit_response(limit, reset_time):
    """Generate 429 Too Many Requests response."""
    retry_after = max(1, reset_time - int(time.time()))
    response = jsonify({
        "success": False,
        "error": "rate_limit_exceeded",
        "message": f"Rate limit exceeded. Limit: {limit} requests per minute.",
        "retry_after": retry_after
    })
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    response.headers['X-RateLimit-Limit'] = str(limit)
    response.headers['X-RateLimit-Remaining'] = '0'
    response.headers['X-RateLimit-Reset'] = str(reset_time)
    return response


def add_rate_limit_headers(response, limit, remaining, reset_time):
    """Add rate limit headers to response."""
    if RATE_LIMIT_ENABLED:
        response.headers['X-RateLimit-Limit'] = str(limit)
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        response.headers['X-RateLimit-Reset'] = str(reset_time)
    return response


def rate_limit(f):
    """
    Decorator to apply rate limiting to a route.
    
    Usage:
        @app.route('/api/v1/endpoint')
        @rate_limit
        def endpoint():
            return jsonify({"success": True})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed, limit, remaining, reset_time = check_rate_limit()
        
        if not allowed:
            return rate_limit_response(limit, reset_time)
        
        # Store for after_request handler
        g.rate_limit_info = (limit, remaining, reset_time)
        
        response = f(*args, **kwargs)
        
        # Add headers to response
        if hasattr(response, 'headers'):
            add_rate_limit_headers(response, limit, remaining, reset_time)
        
        return response
    
    return decorated_function


def init_rate_limiter(app):
    """
    Initialize rate limiter for Flask app.
    Adds after_request handler to include rate limit headers.
    
    Usage:
        from rate_limiter import init_rate_limiter
        init_rate_limiter(app)
    """
    @app.after_request
    def add_rate_limit_headers_after(response):
        if hasattr(g, 'rate_limit_info'):
            limit, remaining, reset_time = g.rate_limit_info
            add_rate_limit_headers(response, limit, remaining, reset_time)
        return response
    
    logger.info("Rate limiter initialized | enabled=%s default=%d auth=%d staked=%d",
                RATE_LIMIT_ENABLED, RATE_LIMIT_DEFAULT, RATE_LIMIT_AUTHENTICATED, RATE_LIMIT_STAKED)
    
    return app


# === Public Endpoint Rate Limiting Middleware ===

# List of public endpoints that should be rate limited
PUBLIC_ENDPOINTS = [
    '/health',
    '/api/v1/bounties',
    '/api/v1/reputation',
    '/api/v1/llm',
    '/api/v1/scrape',
    '/api/v1/tasks',
    '/api/v1/nodes',
]


def should_rate_limit(path):
    """Check if path should be rate limited."""
    if not RATE_LIMIT_ENABLED:
        return False
    
    for endpoint in PUBLIC_ENDPOINTS:
        if path.startswith(endpoint):
            return True
    
    return False


def rate_limit_middleware(app):
    """
    Apply rate limiting as middleware to all public endpoints.
    
    Usage:
        from rate_limiter import rate_limit_middleware
        rate_limit_middleware(app)
    """
    original_wsgi_app = app.wsgi_app
    
    def rate_limited_wsgi_app(environ, start_response):
        with app.request_context(environ):
            if should_rate_limit(request.path):
                allowed, limit, remaining, reset_time = check_rate_limit()
                
                if not allowed:
                    response = rate_limit_response(limit, reset_time)
                    return response(environ, start_response)
                
                # Store for header injection
                environ['rate_limit_info'] = (limit, remaining, reset_time)
        
        return original_wsgi_app(environ, start_response)
    
    app.wsgi_app = rate_limited_wsgi_app
    
    # Add after_request handler for headers
    init_rate_limiter(app)
    
    return app
