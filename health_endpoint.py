"""Extended Health Check Endpoint for Bounty #90

Secure health endpoint that checks service status without
exposing internal system details.
"""
import os
import json
import time

SERVICE_START_TIME = time.time()
DATA_FILE = "/app/data/bounty_reviews.json"


def check_services():
    """Check if required services are available.
    
    Returns status indicators only, no implementation details.
    """
    # Database check - verify primary data file is accessible
    database_ok = False
    try:
        if os.path.exists(DATA_FILE) and os.access(DATA_FILE, os.R_OK):
            database_ok = True
    except Exception:
        pass
    
    # Discord check - verify webhook is configured
    discord_ok = bool(os.environ.get('DISCORD_WEBHOOK_URL', '').strip())
    
    # AI API check - verify at least one AI provider is configured
    ai_ok = bool(
        os.environ.get('GEMINI_KEY', '').strip() or 
        os.environ.get('AI_API_KEY', '').strip() or 
        os.environ.get('ANTHROPIC_KEY', '').strip()
    )
    
    return {
        'database': 'ok' if database_ok else 'degraded',
        'discord': 'ok' if discord_ok else 'degraded',
        'ai_api': 'ok' if ai_ok else 'degraded'
    }


def get_uptime():
    """Get service uptime in seconds."""
    return int(time.time() - SERVICE_START_TIME)


def get_open_tasks():
    """Count open/pending/active tasks from data file."""
    try:
        if os.path.exists(DATA_FILE) and os.access(DATA_FILE, os.R_OK):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                tasks = data.get('tasks', [])
                return sum(1 for t in tasks 
                          if isinstance(t, dict) 
                          and t.get('status', '').lower() in ('open', 'pending', 'active'))
    except Exception:
        pass
    return 0


def get_active_nodes_count(get_active_nodes_func):
    """Get count of active nodes with error handling."""
    try:
        return len(get_active_nodes_func())
    except Exception:
        return 0


def extended_health_check(ai_client, claude_client, get_active_nodes_func):
    """Extended health endpoint implementation.
    
    Returns service health status without exposing internal details.
    
    Returns:
        tuple: (response_dict, http_status_code)
               Healthy = 200, Degraded = 503
    """
    # Service health checks
    services = check_services()
    
    # Determine overall status
    degraded = any(s != 'ok' for s in services.values())
    status = 'degraded' if degraded else 'healthy'
    http_code = 503 if degraded else 200
    
    # Build response (minimal info for health monitoring)
    response = {
        'status': status,
        'version': '3.4.0',
        'uptime_seconds': get_uptime(),
        'services': services,
        'active_nodes': get_active_nodes_count(get_active_nodes_func),
        'open_tasks': get_open_tasks(),
        'ai': bool(ai_client),
        'claude': bool(claude_client),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }
    
    return response, http_code
