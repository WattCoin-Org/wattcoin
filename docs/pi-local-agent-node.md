# Raspberry Pi Local Agent Node (Bounty #16)

Minimal scaffold for a Pi local agent that can register, poll tasks, execute task types, report completion, and expose a dashboard.

## Features
- Registration + task polling against configurable API base URL
- Two built-in executable task types:
  - `data_validation`
  - `file_processing`
- Local SQLite earnings/history tracking
- Flask dashboard (`/`) for node stats
- Mock mode (`WATT_MOCK_MODE=1`) for offline testing

## Quick Start
```bash
cd pi/local_agent_node
./install.sh
. .venv/bin/activate
python agent.py
FLASK_APP=dashboard.py flask run --host 0.0.0.0 --port 8787
```

## Environment
- `WATT_API_BASE` (default: `http://127.0.0.1:5000`)
- `WATT_NODE_ID` (default: `pi-local-agent`)
- `WATT_MOCK_MODE` (`1` default, set `0` to use network)
- `WATT_AGENT_DATA_DIR` (default: `./pi/local_agent_node/data`)
