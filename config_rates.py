import os

class RateLimitConfig:
    """
    Centralized configuration for API rate limits.
    Allows easy tuning via environment variables without code changes.
    """
    
    # Global default (fallback)
    DEFAULT = os.getenv("RATELIMIT_DEFAULT", "100 per minute")
    
    # Expensive operations
    SCRAPE = os.getenv("RATELIMIT_SCRAPE", "10 per minute")  # High cost (bandwidth + processing)
    LLM = os.getenv("RATELIMIT_LLM", "10 per minute")        # High cost (API fees)
    REGISTER = os.getenv("RATELIMIT_REGISTER", "5 per hour") # Critical security (prevent spam nodes)
    
    # Standard API endpoints
    NODES_READ = os.getenv("RATELIMIT_NODES_READ", "100 per minute")
    BOUNTY_READ = os.getenv("RATELIMIT_BOUNTY_READ", "100 per minute")
    TASKS = os.getenv("RATELIMIT_TASKS", "100 per minute")
    
    # UI/Frontend endpoints
    UI_WSI = os.getenv("RATELIMIT_UI", "200 per minute")     # Higher limit for UI interactions
    
    # Webhooks
    WEBHOOKS = os.getenv("RATELIMIT_WEBHOOKS", "50 per minute")
    
    @staticmethod
    def get_tier_limit(tier: str) -> str:
        """Get rate limit string for a specific API key tier"""
        limits = {
            "basic": "500 per hour",
            "premium": "2000 per hour",
            "enterprise": "10000 per hour"
        }
        return limits.get(tier, limits["basic"])
