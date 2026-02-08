from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config_rates import RateLimitConfig
import logging

# Initialize Limiter without app (init_app pattern)
# Use 'swallow_errors' and 'in_memory_fallback' for high availability
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[l.strip() for l in RateLimitConfig.DEFAULT.split(",")],
    storage_uri=RateLimitConfig.STORAGE_URI,
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
    headers_enabled=True,
    swallow_errors=True,            # Don't crash if Redis is down
    in_memory_fallback_enabled=True # Fallback to RAM if Redis fails (CRITICAL)
)

def setup_limiter_logging(app):
    """Register logger for limiter errors after app is available"""
    logger = logging.getLogger("flask_limiter")
    # Limiter will now log to the standard app logger
    pass
