"""
WattCoin IoT Bridge — enables smart home device data monetization on the WattCoin network.

Adapters:
- MQTTAdapter: Connect to any MQTT broker (local or cloud)
- ZigbeeAdapter: Connect via Zigbee2MQTT HTTP API
- HttpApiAdapter: Direct device APIs (Kasa, Hue)
- MockAdapter: Testing without hardware

Usage:
    from iot_bridge.bridge import IoTBridge
    bridge = IoTBridge(config)
    bridge.start()
"""
from .bridge import IoTBridge
from .mqtt_adapter import MQTTAdapter
from .zigbee_adapter import ZigbeeAdapter
from .http_api_adapter import HttpApiAdapter
from .mock_adapter import MockAdapter

__version__ = "1.0.0"
__all__ = ["IoTBridge", "MQTTAdapter", "ZigbeeAdapter", "HttpApiAdapter", "MockAdapter"]
