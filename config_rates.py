import os

class RateLimitConfig:
    """
    Centralized configuration for API rate limits.
    
    JUSTIFICATION:
    Moving hardcoded limits to a centralized config allows for consistent 
    enforcement across nodes and enables DevOps to fine-tune limits via 
    environment variables without code redeploys.
    """
    
    # Storage
    STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    
    # Global default: Restoration of original dual limits (1000/hr, 100/min)
    # Passed as a single string for standard Flask-Limiter parsing compatibility
    DEFAULT = "1000 per hour, 100 per minute"
    
    # Shared limits mapped from original hardcoded values
    SCRAPE = os.getenv("RATELIMIT_SCRAPE", "10 per minute")
    LLM = os.getenv("RATELIMIT_LLM", "10 per minute")
    REGISTER = os.getenv("RATELIMIT_REGISTER", "5 per hour")
    NODES_READ = os.getenv("RATELIMIT_NODES_READ", "100 per minute")
    BOUNTY_READ = os.getenv("RATELIMIT_BOUNTY_READ", "100 per minute")
    TASKS = os.getenv("RATELIMIT_TASKS", "100 per minute")
    UI_WSI = os.getenv("RATELIMIT_UI", "200 per minute")
    WEBHOOKS = os.getenv("RATELIMIT_WEBHOOKS", "50 per minute")
