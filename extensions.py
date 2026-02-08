from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config_rates import RateLimitConfig

# Initialize Limiter without app (init_app pattern)
# This allows blueprints to import 'limiter' without circular dependencies
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[RateLimitConfig.DEFAULT],
    storage_uri=RateLimitConfig.STORAGE_URI, # Prioritize Redis if available (from config_rates)
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
    headers_enabled=True,
)
