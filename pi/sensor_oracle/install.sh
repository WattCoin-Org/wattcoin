#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip

cat <<'EOF'
✅ Sensor oracle scaffold installed.
Run once:
  .venv/bin/python oracle.py --once
Run continuously:
  .venv/bin/python oracle.py
EOF
