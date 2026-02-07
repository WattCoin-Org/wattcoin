"""
Rate Limiter Middleware for WattCoin API
Bounty: https://github.com/WattCoin-Org/wattcoin/issues/88

Implements rate limiting on public API endpoints to prevent abuse.
- Default: 60 requests/minute per IP for public endpoints
- Higher limits for authenticated/staked wallets
- Rate limit headers in responses
- 429 Too Many Requests with retry-after header
- Configurable via environment variables
"""

import os
import time
import logging
from flask import request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger("wattcoin.rate_limiter")

# =============================================================================
# CONFIGURATION via Environment Variables
# =============================================================================
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60 per minute")
RATE_LIMIT_AUTHENTICATED = os.getenv("RATE_LIMIT_AUTHENTICATED", "200 per minute")
RATE_LIMIT_PREMIUM = os.getenv("RATE_LIMIT_PREMIUM", "500 per minute")
RATE_LIMIT_STAKED = os.getenv("RATE_LIMIT_STAKED", "1000 per minute")
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", os.getenv("REDIS_URL", "memory://"))

# Endpoint-specific limits
RATE_LIMIT_SCRAPE = os.getenv("RATE_LIMIT_SCRAPE", "30 per minute")
RATE_LIMIT_LLM = os.getenv("RATE_LIMIT_LLM", "20 per minute")
RATE_LIMIT_HEALTH = os.getenv("RATE_LIMIT_HEALTH", "120 per minute")


def get_client_identifier():
    """
    Get client identifier for rate limiting.
    Priority: wallet address > API key > IP address
    """
    # Check if wallet address is available (set by authentication middleware)
    wallet = getattr(g, 'wallet_address', None)
    if wallet:
        return f"wallet:{wallet}"
    
    # Check for API key in headers
    api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if api_key and len(api_key) > 10:
        return f"apikey:{api_key[:20]}"
    
    # Fallback to IP address
    return get_remote_address()


def get_dynamic_limit():
    """
    Determine rate limit dynamically based on client authentication level.
    Called by limiter.limit() decorator with dynamic=True.
    """
    # Check for staked wallet (highest priority) 
    staked = getattr(g, 'is_staked', False)
    if staked:
        logger.debug(f"Rate limit: STAKED ({RATE_LIMIT_STAKED})")
        return RATE_LIMIT_STAKED
    
    # Check for premium tier API key
    tier = getattr(g, 'api_tier', None)
    if tier == 'premium':
        logger.debug(f"Rate limit: PREMIUM ({RATE_LIMIT_PREMIUM})")
        return RATE_LIMIT_PREMIUM
    
    # Check for basic authentication (API key or wallet)
    if tier == 'basic':
        logger.debug(f"Rate limit: AUTHENTICATED ({RATE_LIMIT_AUTHENTICATED})")
        return RATE_LIMIT_AUTHENTICATED
        
    if getattr(g, 'wallet_address', None):
        logger.debug(f"Rate limit: WALLET AUTH ({RATE_LIMIT_AUTHENTICATED})")
        return RATE_LIMIT_AUTHENTICATED
    
    # Default public rate limit
    logger.debug(f"Rate limit: PUBLIC ({RATE_LIMIT_DEFAULT})")
    return RATE_LIMIT_DEFAULT


def create_rate_limiter(app):
    """
    Create and configure Flask-Limiter instance with WattCoin-specific settings.
    
    Usage:
        from rate_limiter import create_rate_limiter, RATE_LIMIT_SCRAPE
        
        limiter = create_rate_limiter(app)
        
        @app.route('/api/v1/scrape')
        @limiter.limit(RATE_LIMIT_SCRAPE)
        def scrape():
            ...
    """
    limiter = Limiter(
        key_func=get_client_identifier,
        app=app,
        storage_uri=RATE_LIMIT_STORAGE_URI,
        storage_options={"socket_connect_timeout": 30},
        default_limits=[RATE_LIMIT_DEFAULT],
        strategy="fixed-window",
        headers_enabled=True,
    )
    
    # Register custom 429 error handler
    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Custom handler for rate limit exceeded (429) responses."""
        # Parse retry time from error description
        retry_after = 60  # default
        if hasattr(e, 'description') and e.description:
            try:
                # Try to extract seconds from description like "60 seconds"
                parts = str(e.description).split()
                for i, part in enumerate(parts):
                    if part.isdigit():
                        retry_after = int(part)
                        break
            except:
                pass
        
        logger.warning(
            f"Rate limit exceeded | ip={request.remote_addr} | "
            f"path={request.path} | retry_after={retry_after}s"
        )
        
        response = jsonify({
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please slow down and try again later.",
            "retry_after": retry_after,
            "hint": "Authenticated users and staked wallets have higher rate limits."
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        
        return response
    
    logger.info(
        f"Rate limiter initialized | default={RATE_LIMIT_DEFAULT} | "
        f"authenticated={RATE_LIMIT_AUTHENTICATED} | premium={RATE_LIMIT_PREMIUM} | "
        f"staked={RATE_LIMIT_STAKED} | storage={RATE_LIMIT_STORAGE_URI}"
    )
    
    return limiter


# =============================================================================
# RATE LIMIT DECORATORS (for convenient use in endpoints)
# =============================================================================
# These can be used directly with @limiter.limit(LIMIT_NAME)

# Standard limits
PUBLIC_LIMIT = RATE_LIMIT_DEFAULT
AUTHENTICATED_LIMIT = RATE_LIMIT_AUTHENTICATED  
PREMIUM_LIMIT = RATE_LIMIT_PREMIUM
STAKED_LIMIT = RATE_LIMIT_STAKED

# Endpoint-specific limits
SCRAPE_LIMIT = RATE_LIMIT_SCRAPE
LLM_LIMIT = RATE_LIMIT_LLM
HEALTH_LIMIT = RATE_LIMIT_HEALTH


def exempt_when_authenticated(func=None):
    """
    Decorator to exempt authenticated users from default rate limits.
    They still get their tier-specific limits applied.
    
    Usage:
        @limiter.limit(get_dynamic_limit)
        @exempt_when_authenticated
        def my_endpoint():
            ...
    """
    def decorator(f):
        f._rate_limit_exempt_when_authenticated = True
        return f
    
    if func:
        return decorator(func)
    return decorator
