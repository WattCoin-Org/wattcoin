from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config_rates import RateLimitConfig

# Initialize Limiter without app (init_app pattern)
# Use 'swallow_errors' and 'in_memory_fallback' to ensure high availability.
# If Redis is unavailable, 'swallow_errors' prevents crashes, 
# while 'in_memory_fallback_enabled' ensures rate limiting still works locally.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=RateLimitConfig.DEFAULT,
    storage_uri=RateLimitConfig.STORAGE_URI,
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
    headers_enabled=True,
    swallow_errors=True,            # Robustness: Don't raise on connection errors
    in_memory_fallback_enabled=True # Fault Tolerance: Fallback to local memory
)
