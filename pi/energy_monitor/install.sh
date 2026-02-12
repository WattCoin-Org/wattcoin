#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install requests python-kasa

echo "Installed. Example run:"
echo "  WATT_DEV_SIGNING_SECRET=dev-secret python monitor.py --base-url https://api.wattcoin.org --wallet YOUR_WALLET --source mock --mock-file mock_meter.json --once"
