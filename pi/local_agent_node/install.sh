#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install flask requests

echo "✅ Installed local agent node scaffold"
echo "Run agent:   .venv/bin/python agent.py"
echo "Run dashboard: FLASK_APP=dashboard.py .venv/bin/flask run --host 0.0.0.0 --port 8787"
