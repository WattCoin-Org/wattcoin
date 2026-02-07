"""
Health Check API - System status monitoring endpoint
v1.0.0 - Initial implementation for bounty issue #90
"""

from flask import Blueprint, jsonify
import os
import time
import json
from datetime import datetime, timezone

health_bp = Blueprint('health', __name__)

# Track server start time for uptime calculation
_start_time = time.time()

# === Config ===
DATA_DIR = os.environ.get('DATA_DIR', '/app/data')
NODES_FILE = os.environ.get('NODES_FILE', os.path.join(DATA_DIR, 'nodes.json'))
TASKS_FILE = os.environ.get('TASKS_FILE', os.path.join(DATA_DIR, 'tasks.json'))
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
VERSION = "3.2.0"


def check_database():
    """Check if database files are readable."""
    try:
        # Check if data directory exists
        if not os.path.exists(DATA_DIR):
            return "degraded"
        
        # Check nodes.json
        if os.path.exists(NODES_FILE):
            with open(NODES_FILE, 'r') as f:
                json.load(f)
        
        # Check tasks.json
        if os.path.exists(TASKS_FILE):
            with open(TASKS_FILE, 'r') as f:
                json.load(f)
        
        return "ok"
    except Exception:
        return "error"


def check_discord():
    """Check if Discord webhook is configured."""
    if DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL.startswith('https://discord.com/api/webhooks/'):
        return "ok"
    elif DISCORD_WEBHOOK_URL:
        return "degraded"
    else:
        return "not_configured"


def check_ai_api():
    """Check if AI API keys are configured (no actual API call to stay fast)."""
    if OPENAI_API_KEY or ANTHROPIC_API_KEY:
        return "ok"
    else:
        return "not_configured"


def get_active_node_count():
    """Get count of active nodes from nodes.json."""
    try:
        if not os.path.exists(NODES_FILE):
            return 0
        
        with open(NODES_FILE, 'r') as f:
            data = json.load(f)
        
        nodes = data.get('nodes', {})
        current_time = time.time()
        heartbeat_timeout = 120  # 2 minutes
        
        active_count = 0
        for node_id, node_data in nodes.items():
            last_heartbeat = node_data.get('last_heartbeat', 0)
            if current_time - last_heartbeat < heartbeat_timeout:
                active_count += 1
        
        return active_count
    except Exception:
        return 0


def get_open_task_count():
    """Get count of open tasks from tasks.json."""
    try:
        if not os.path.exists(TASKS_FILE):
            return 0
        
        with open(TASKS_FILE, 'r') as f:
            data = json.load(f)
        
        tasks = data.get('tasks', [])
        open_count = sum(1 for task in tasks if task.get('status') == 'open')
        return open_count
    except Exception:
        return 0


@health_bp.route('/api/v1/health', methods=['GET'])
def health_check():
    """
    Health check endpoint - returns system status.
    
    Returns:
        200: System healthy
        503: System degraded
    
    Response format:
    {
        "status": "healthy" | "degraded",
        "version": "3.2.0",
        "uptime_seconds": 84600,
        "services": {
            "database": "ok" | "degraded" | "error",
            "discord": "ok" | "degraded" | "not_configured",
            "ai_api": "ok" | "not_configured"
        },
        "active_nodes": 2,
        "open_tasks": 1,
        "timestamp": "2026-02-07T..."
    }
    """
    # Check all services
    db_status = check_database()
    discord_status = check_discord()
    ai_status = check_ai_api()
    
    # Get counts
    active_nodes = get_active_node_count()
    open_tasks = get_open_task_count()
    
    # Calculate uptime
    uptime_seconds = int(time.time() - _start_time)
    
    # Determine overall status
    # Degraded if database has issues or no AI API configured
    if db_status == "error":
        overall_status = "degraded"
    elif db_status == "degraded":
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    response = {
        "status": overall_status,
        "version": VERSION,
        "uptime_seconds": uptime_seconds,
        "services": {
            "database": db_status,
            "discord": discord_status,
            "ai_api": ai_status
        },
        "active_nodes": active_nodes,
        "open_tasks": open_tasks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    status_code = 200 if overall_status == "healthy" else 503
    return jsonify(response), status_code
