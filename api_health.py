from flask import Blueprint, jsonify
import os
import time
import json
from datetime import datetime, timezone
import logging

health_bp = Blueprint('health', __name__)
logger = logging.getLogger("wattcoin.health")

# Track startup time
START_TIME = time.time()

# Version updated to current
VERSION = "3.2.2"

@health_bp.route('/api/v1/health', methods=['GET'])
def health():
    """
    System health check endpoint.
    Returns status of database, external services, and network metrics.
    """
    healthy = True
    services = {}
    
    # 1. Database Check (JSON files readable)
    data_dir = os.getenv('DATA_DIR', '/app/data')
    db_files = ['nodes.json', 'node_jobs.json', 'tasks.json', 'bounty_reviews.json']
    db_status = "ok"
    for db_file in db_files:
        path = os.path.join(data_dir, db_file)
        if os.path.exists(path):
            if not os.access(path, os.R_OK):
                db_status = "degraded"
                healthy = False
                logger.warning(f"Database file not readable: {db_file}")
    services['database'] = db_status

    # 2. Discord Webhook Check
    discord_url = os.getenv('DISCORD_WEBHOOK_URL')
    services['discord'] = "ok" if discord_url and discord_url.startswith('https://') else "missing"
    if services['discord'] == "missing":
        healthy = False

    # 3. AI API Check (Keys present)
    ai_key = os.getenv('AI_API_KEY')
    claude_key = os.getenv('CLAUDE_API_KEY')
    services['ai_api'] = "ok" if ai_key and claude_key else "missing"
    if services['ai_api'] == "missing":
        healthy = False

    # 4. Active Node Count
    active_nodes = 0
    try:
        from api_nodes import get_active_nodes
        active_nodes = len(get_active_nodes())
    except Exception as e:
        logger.error(f"Error counting active nodes: {e}")

    # 5. Open Task Count
    open_tasks = 0
    try:
        from api_tasks import load_tasks
        tasks_data = load_tasks()
        open_tasks = sum(1 for t in tasks_data.get("tasks", {}).values() if t.get("status") == "open")
    except Exception as e:
        logger.error(f"Error counting open tasks: {e}")

    # Final Status
    status_code = 200 if healthy else 503
    
    response = {
        "status": "healthy" if healthy else "degraded",
        "version": VERSION,
        "uptime_seconds": int(time.time() - START_TIME),
        "services": services,
        "active_nodes": active_nodes,
        "open_tasks": open_tasks,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }

    return jsonify(response), status_code
