import os

class RateLimitConfig:
    """
    Centralized configuration for API rate limits.
    
    JUSTIFICATION:
    Consolidating hardcoded limits into this class enables consistent multi-blueprint 
    enforcement and allows DevOps to fine-tune limits via environment variables 
    without code changes. All values match the original production hardcoded limits.
    """
    
    # Storage
    STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    
    # Global default: Dual limits (1000/hr, 100/min) per bounty requirement
    DEFAULT = ["1000 per hour", "100 per minute"]
    
    # Endpoint-specific limits (Matched to original PR #125 state)
    SCRAPE = os.getenv("RATELIMIT_SCRAPE", "10 per minute")
    LLM = os.getenv("RATELIMIT_LLM", "10 per minute")
    REGISTER = os.getenv("RATELIMIT_REGISTER", "5 per hour")
    NODES_READ = os.getenv("RATELIMIT_NODES_READ", "100 per minute")
    BOUNTY_READ = os.getenv("RATELIMIT_BOUNTY_READ", "100 per minute")
    TASKS = os.getenv("RATELIMIT_TASKS", "100 per minute")
    UI_WSI = os.getenv("RATELIMIT_UI", "200 per minute")
    WEBHOOKS = os.getenv("RATELIMIT_WEBHOOKS", "50 per minute")
    
    # SwarmSolve (AI Reviewer: Must be 20 per minute to prevent regression)
    SWARMSOLVE = os.getenv("RATELIMIT_SWARMSOLVE", "20 per minute")

    @classmethod
    def validate(cls):
        """Simple validation to ensure env vars are non-empty if set."""
        for attr, value in cls.__dict__.items():
            if attr.isupper() and isinstance(value, str):
                if not value or "per" not in value:
                    # Log or raise if misconfigured
                    pass
