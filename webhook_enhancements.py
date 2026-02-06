"""
Enhanced Logging and Security Module for api_webhooks.py

This module provides additional logging and security features that can be
imported and used alongside the existing api_webhooks.py without modifying
core payment functionality.

Usage:
    from webhook_enhancements import RequestIdFilter, retry_with_backoff
    
    # Add to existing api_webhooks.py:
    # 1. Import the enhancements
    # 2. Apply logging configuration
    # 3. Use retry decorator on external API calls
"""

import logging
import functools
import time
from flask import g

# =============================================================================
# ENHANCED LOGGING CONFIGURATION
# =============================================================================

class RequestIdFilter(logging.Filter):
    """Add request ID to log records for request tracing."""
    def filter(self, record):
        record.request_id = getattr(g, 'request_id', 'N/A')
        return True

def setup_enhanced_logging(app):
    """
    Setup enhanced logging for the webhook blueprint.
    Call this in your app initialization.
    
    Args:
        app: Flask application instance
    """
    import os
    
    # Ensure log directory exists
    os.makedirs('/app/logs', exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(request_id)s] - %(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('/app/logs/webhooks.log')
        ]
    )
    
    logger = logging.getLogger('webhook_handler')
    logger.addFilter(RequestIdFilter())
    
    return logger

# =============================================================================
# RETRY DECORATOR WITH EXPONENTIAL BACKOFF
# =============================================================================

def retry_with_backoff(max_retries=3, base_delay=1):
    """
    Decorator to retry function calls with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds (doubles with each retry)
    
    Usage:
        @retry_with_backoff(max_retries=3, base_delay=1)
        def my_api_call():
            # This will retry up to 3 times with delays of 1s, 2s, 4s
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import logging
            logger = logging.getLogger('webhook_handler')
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay}s...",
                            extra={'attempt': attempt + 1, 'retry_delay': delay}
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_retries} attempts failed: {e}",
                            extra={'attempt': attempt + 1, 'error': str(e)}
                        )
            
            raise last_exception
        return wrapper
    return decorator

# =============================================================================
# REQUEST TRACKING MIDDLEWARE
# =============================================================================

def setup_request_tracking(blueprint):
    """
    Setup request tracking middleware for a Flask blueprint.
    Adds request ID and timing to all requests.
    
    Args:
        blueprint: Flask Blueprint instance
    """
    import uuid
    
    @blueprint.before_request
    def before_request():
        """Set request ID and start timer for each request."""
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.time()
        
        import logging
        logger = logging.getLogger('webhook_handler')
        from flask import request
        logger.info(f"Request started: {request.method} {request.path}")
    
    @blueprint.after_request
    def after_request(response):
        """Log response time and status."""
        duration = time.time() - g.start_time
        
        import logging
        logger = logging.getLogger('webhook_handler')
        logger.info(
            f"Request completed: {response.status_code} in {duration:.3f}s",
            extra={
                'status_code': response.status_code,
                'duration_ms': int(duration * 1000)
            }
        )
        return response

# =============================================================================
# USAGE EXAMPLE (for integration into api_webhooks.py)
# =============================================================================

"""
# Add these imports at the top of api_webhooks.py:
from webhook_enhancements import (
    setup_enhanced_logging, 
    retry_with_backoff,
    setup_request_tracking
)

# Add after blueprint creation:
setup_request_tracking(webhooks_bp)
logger = setup_enhanced_logging(app)

# Then add @retry_with_backoff decorator to external API calls:
# @retry_with_backoff(max_retries=3)
# def get_bounty_amount(issue_number):
#     ... existing code ...

# @retry_with_backoff(max_retries=3)
# def post_github_comment(issue_number, comment):
#     ... existing code ...

# @retry_with_backoff(max_retries=3)
# def trigger_ai_review(pr_number):
#     ... existing code ...

# @retry_with_backoff(max_retries=3)
# def auto_merge_pr(pr_number, review_score):
#     ... existing code ...
"""
