# Raspberry Pi IoT Bridge (Bounty #17)

This scaffold provides a minimal, mergeable starting point for the WattCoin IoT bridge:

- Protocol support (mock):
  - MQTT
  - Zigbee2MQTT
- State reporting to configurable API endpoint
- Command relay to protocol adapter
- Local config UI (`/config`) for device mapping updates

## Quickstart

```bash
cd pi/iot_bridge
python3 bridge.py
```

Run local config UI:

```bash
python3 config_ui.py
# open http://localhost:8787/config
```

## Environment variables

- `WATT_API_BASE_URL` (default: `http://localhost:8000`)
- `WATT_API_KEY` (optional)
- `WATT_MOCK_MODE` (`1` for mock mode, default on)

## Notes

- Uses graceful error handling when API is unreachable.
- Designed so real protocol clients can replace mock adapters with minimal changes.
