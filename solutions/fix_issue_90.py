```python
import os
import json
import datetime
from flask import Flask, jsonify

app = Flask(__name__)

# Assuming these are set somewhere in the application
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
AI_API_KEY = os.getenv('AI_API_KEY', '')
DATA_FILE_PATH = 'data.json'  # Example path to data file

@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Check Data Files Readability
        data_files_readable = os.path.isfile(DATA_FILE_PATH) and os.access(DATA_FILE_PATH, os.R_OK)

        # Check Discord Webhook Configuration
        discord_configured = bool(DISCORD_WEBHOOK_URL)

        # Check AI API Key Presence
        ai_api_key_present = bool(AI_API_KEY)

        # Count Active Nodes and Open Tasks
        active_nodes = 0
        open_tasks = 0
        if data_files_readable:
            with open(DATA_FILE_PATH, 'r') as file:
                data = json.load(file)
                active_nodes = len(data.get('nodes', []))
                open_tasks = len(data.get('tasks', []))

        # Determine overall status
        services_status = {
            "database": "ok" if data_files_readable else "degraded",
            "discord": "ok" if discord_configured else "degraded",
            "ai_api": "ok" if ai_api_key_present else "degraded"
        }
        overall_status = "healthy" if all(status == "ok" for status in services_status.values()) else "degraded"

        # Construct response
        response = {
            "status": overall_status,
            "version": "3.2.2",
            "uptime_seconds": 84600,  # This should be dynamically calculated
            "services": services_status,
            "active_nodes": active_nodes,
            "open_tasks": open_tasks,
            "timestamp": datetime.datetime.now().isoformat()
        }

        # Return appropriate HTTP status
        http_status = 200 if overall_status == "healthy" else 503
        return jsonify(response), http_status

    except Exception as e:
        # Log the exception
        app.logger.error(f"Health check failed: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == '__main__':
    app.run()
```