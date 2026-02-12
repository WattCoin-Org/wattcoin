#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip

echo "✅ Inference relay scaffold installed."
echo "Run: ${VENV_DIR}/bin/python ${ROOT_DIR}/relay.py --once"
