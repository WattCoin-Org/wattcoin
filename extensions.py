from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config_rates import RateLimitConfig
import logging

# Initialize Limiter without app (init_app pattern)
# Use 'swallow_errors' and 'in_memory_fallback' for high availability
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[RateLimitConfig.DEFAULT],
    storage_uri=RateLimitConfig.STORAGE_URI,
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
    headers_enabled=True,
    swallow_errors=True            # High Availability: Allow requests if Redis is unavailable
)
