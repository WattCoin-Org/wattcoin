import os

class RateLimitConfig:
    """
    Centralized configuration for API rate limits.
    Pure data class to avoid circular imports.
    """
    
    # Storage
    STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    
    # Global default: Restoration of original dual limits
    # Comma-separated string is most compatible with Flask-Limiter parsing
    DEFAULT = "1000 per hour, 100 per minute"
    
    # Expensive operations
    SCRAPE = os.getenv("RATELIMIT_SCRAPE", "10 per minute")
    LLM = os.getenv("RATELIMIT_LLM", "10 per minute")
    REGISTER = os.getenv("RATELIMIT_REGISTER", "5 per hour")
    
    # Standard API endpoints
    NODES_READ = os.getenv("RATELIMIT_NODES_READ", "100 per minute")
    BOUNTY_READ = os.getenv("RATELIMIT_BOUNTY_READ", "100 per minute")
    TASKS = os.getenv("RATELIMIT_TASKS", "100 per minute")
    
    # UI/Frontend endpoints
    UI_WSI = os.getenv("RATELIMIT_UI", "200 per minute")
    
    # Webhooks
    WEBHOOKS = os.getenv("RATELIMIT_WEBHOOKS", "50 per minute")

    @staticmethod
    def get_tier_limit(tier: str) -> str:
        """Helper for tier-based lookup"""
        limits = {
            "basic": "500 per hour",
            "premium": "2000 per hour",
            "enterprise": "10000 per hour"
        }
        return limits.get(tier, "500 per hour")
