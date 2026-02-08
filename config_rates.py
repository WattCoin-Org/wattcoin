import os
import logging

# Set up logger
logger = logging.getLogger("wattcoin.config")

def _validate_limit(limit_str: str) -> bool:
    """Internal validator for 'X per Y' format"""
    if not isinstance(limit_str, str): return False
    parts = limit_str.lower().split(" per ")
    if len(parts) != 2: return False
    if not parts[0].strip().replace(" ", "").isdigit(): return False
    units = ["second", "minute", "hour", "day", "month", "year"]
    return any(unit in parts[1] for unit in units)

def _get_env_limit(env_var: str, default: str) -> str:
    """Validated fetch for environment variables with logging on failure"""
    val = os.getenv(env_var, default)
    if _validate_limit(val):
        return val
    logger.warning(f"Invalid rate limit format for {env_var}: '{val}'. Falling back to default: '{default}'")
    return default

class RateLimitConfig:
    """
    Centralized configuration for API rate limits.
    Allows easy tuning via environment variables without code changes.
    """
    
    # Storage
    STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    
    # Global default (original dual limits: 1000/hr, 100/min)
    # Passed as a list to flask-limiter constructor
    DEFAULT = ["1000 per hour", "100 per minute"]
    
    # Tiered limits (backward compatibility backup)
    TIER_BASIC = "500 per hour"
    TIER_PREMIUM = "2000 per hour"
    TIER_ENTERPRISE = "10000 per hour"

    # Expensive operations
    SCRAPE = _get_env_limit("RATELIMIT_SCRAPE", "10 per minute")
    LLM = _get_env_limit("RATELIMIT_LLM", "10 per minute")
    REGISTER = _get_env_limit("RATELIMIT_REGISTER", "5 per hour")
    
    # Standard API endpoints
    NODES_READ = _get_env_limit("RATELIMIT_NODES_READ", "100 per minute")
    BOUNTY_READ = _get_env_limit("RATELIMIT_BOUNTY_READ", "100 per minute")
    TASKS = _get_env_limit("RATELIMIT_TASKS", "100 per minute")
    
    # UI/Frontend endpoints
    UI_WSI = _get_env_limit("RATELIMIT_UI", "200 per minute")
    
    # Webhooks
    WEBHOOKS = _get_env_limit("RATELIMIT_WEBHOOKS", "50 per minute")

    @staticmethod
    def get_tier_limit(tier: str) -> str:
        """Helper for tier-based lookup"""
        limits = {
            "basic": RateLimitConfig.TIER_BASIC,
            "premium": RateLimitConfig.TIER_PREMIUM,
            "enterprise": RateLimitConfig.TIER_ENTERPRISE
        }
        return limits.get(tier, RateLimitConfig.TIER_BASIC)
