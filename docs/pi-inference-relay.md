# Raspberry Pi Inference Relay (Scaffold)

This scaffold is a minimal starting point for bounty **#18** (Raspberry Pi inference relay).

## What it does

- Provides a small relay runner (`pi/inference_relay/relay.py`)
- Supports local mock inference (`--once --prompt "..."`)
- Generates signed API headers (`X-Relay-Id`, `X-Relay-Signature`)
- Optionally submits result payloads to:
  - `POST /api/v1/inference/report`

## Quick start

```bash
cd pi/inference_relay
./install.sh
.venv/bin/python relay.py --once --prompt "Summarize WattCoin"
```

## Environment variables

- `WATT_API_BASE` (default: `http://127.0.0.1:5001`)
- `WATT_RELAY_ID` (default: generated `pi-relay-xxxx`)
- `WATT_RELAY_SECRET` (default: `dev-secret`)
- `WATT_RELAY_MODEL` (default: `tinyllama`)
- `WATT_RELAY_TIMEOUT` (default: `30`)

## Notes

- This is intentionally minimal and safe to merge.
- The current inference implementation is a mock path suitable for wiring and API validation.
- Replace `_mock_infer()` with real local inference runtime (llama.cpp/Ollama/vLLM) in follow-up PRs.
