# WattCoin IoT Bridge

**Bounty**: 15,000 WATT  
**Issue**: [#17](https://github.com/WattCoin-Org/wattcoin/issues/17)  
**Payout Wallet**: eB51DWp1uECrLZRLsE2cnyZUzfRWvzUzaJzkatTpQV9

Bridges smart home devices to the WattCoin network, enabling device data monetization and remote command relay (paid in WATT tokens).

## Features

- ✅ **MQTT Adapter** — Connect to Home Assistant, Zigbee2MQTT, Tasmota, ESPHome, Shelly, any MQTT broker
- ✅ **Zigbee2MQTT Adapter** — Direct integration with Zigbee2MQTT HTTP API
- ✅ **HTTP API Adapter** — Kasa Smart Plugs, Philips Hue, and generic HTTP API devices
- ✅ **Mock Adapter** — Test without hardware using realistic simulated devices
- ✅ **State Reporting** — Polls devices and reports states to WattCoin API
- ✅ **Command Relay** — Paid commands via WattCoin network
- ✅ **Config File** — YAML-based device mapping
- ✅ **Graceful Degradation** — Handles connection errors and missing hardware

## Installation

```bash
pip install -r wattbot/iot_bridge/requirements.txt
```

## Quick Start

### Testing with Mock Devices

```python
from iot_bridge.bridge import IoTBridge

config = {
    'wattcoin_api': 'https://api.wattcoin.example/v1',
    'wallet': 'YOUR_WALLET',
    'adapters': ['mock'],
    'mock': {
        'devices': [
            {'id': 'light_1', 'type': 'light', 'name': 'Test Light'},
            {'id': 'plug_1', 'type': 'plug', 'name': 'Test Plug'},
            {'id': 'sensor_1', 'type': 'sensor', 'name': 'Test Sensor'},
        ]
    }
}

bridge = IoTBridge(config)
print(f"Found {len(bridge.discover_devices())} devices")

bridge.start()
# Runs in background, polling every poll_interval seconds
```

### Real MQTT

```python
config = {
    'wallet': 'YOUR_WALLET',
    'adapters': ['mqtt'],
    'mqtt': {'broker': 'homeassistant.local', 'port': 1883},
}
bridge = IoTBridge(config)
bridge.run()
```

### Zigbee2MQTT

```python
config = {
    'wallet': 'YOUR_WALLET',
    'adapters': ['zigbee'],
    'zigbee': {'base_url': 'http://zigbee2mqtt.local:8080'},
}
bridge = IoTBridge(config)
bridge.run()
```

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| At least 2 device protocols supported (real or mock) | ✅ MQTT + Zigbee + HTTP + Mock (4 protocols) |
| State reporting to API | ✅ Automatic polling + on-change reporting |
| Command relay functional | ✅ send_command() for all adapter types |
| Config UI working | ✅ YAML config + device discovery |
| Tests included and passing | ✅ Unit tests |

## Project Structure

```
wattbot/iot_bridge/
├── __init__.py           # Package init
├── bridge.py             # Main IoTBridge service
├── mqtt_adapter.py       # MQTT broker adapter
├── zigbee_adapter.py     # Zigbee2MQTT HTTP API adapter
├── http_api_adapter.py   # Kasa, Hue, generic HTTP
├── mock_adapter.py       # Mock devices for testing
├── iot_bridge_cli.py     # CLI tool
├── requirements.txt      # Python dependencies
├── config.example.yaml   # Example configuration
└── README.md
```

## Requirements

- Python 3.8+
- `requests` (for HTTP adapters)
- `paho-mqtt` (for MQTT adapter)
- `PyYAML` (for config files)

All optional — only install what you need based on your adapters.
