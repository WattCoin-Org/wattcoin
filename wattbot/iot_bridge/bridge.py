"""
IoTBridge — Main bridge service coordinating device adapters and WattCoin API.
"""
import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("iot-bridge")


class IoTBridge:
    """
    Main IoT Bridge — connects smart home devices to the WattCoin network.
    
    Supports multiple device adapters (MQTT, Zigbee2MQTT, HTTP API, Mock).
    Reports device states to WattCoin API and relays paid commands.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_url = config.get("wattcoin_api", "https://api.wattcoin.example/v1")
        self.wallet = config.get("wallet", "")
        self.poll_interval = config.get("poll_interval", 10)
        self.api_key = config.get("api_key", "")
        
        self._adapters: Dict[str, Any] = {}
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._device_states: Dict[str, Any] = {}
        self._state_lock = threading.Lock()
        self.on_state_change: Optional[Callable[[str, Any], None]] = None
        self.on_command: Optional[Callable[[str, Any, str], bool]] = None
        self.on_error: Optional[Callable[[str, Exception], None]] = None
        
        self._init_adapters()

    def _init_adapters(self):
        adapter_types = self.config.get("adapters", ["mock"])
        from .mqtt_adapter import MQTTAdapter
        from .zigbee_adapter import ZigbeeAdapter
        from .http_api_adapter import HttpApiAdapter
        from .mock_adapter import MockAdapter
        
        adapter_map = {
            "mqtt": MQTTAdapter, "zigbee": ZigbeeAdapter,
            "http": HttpApiAdapter, "kasa": HttpApiAdapter,
            "hue": HttpApiAdapter, "mock": MockAdapter,
        }
        
        for adapter_type in adapter_types:
            adapter_cls = adapter_map.get(adapter_type.lower())
            if adapter_cls is None:
                logger.warning(f"Unknown adapter type: {adapter_type}")
                continue
            adapter_config = self.config.get(adapter_type.lower(), {})
            try:
                adapter = adapter_cls(adapter_config)
                self._adapters[adapter_type] = adapter
                logger.info(f"Initialized {adapter_type} adapter")
            except Exception as e:
                logger.error(f"Failed to init {adapter_type}: {e}")

    def discover_devices(self) -> List[Dict[str, Any]]:
        all_devices = []
        for name, adapter in self._adapters.items():
            try:
                devices = adapter.discover()
                for device in devices:
                    device["adapter"] = name
                    device["id"] = device.get("id", str(uuid.uuid4()))
                all_devices.extend(devices)
            except Exception as e:
                logger.error(f"Discovery failed for {name}: {e}")
        return all_devices

    def get_device_state(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._state_lock:
            return self._device_states.get(device_id)

    def get_all_states(self) -> Dict[str, Any]:
        with self._state_lock:
            return dict(self._device_states)

    def _poll_states(self):
        while self._running:
            for name, adapter in self._adapters.items():
                try:
                    states = adapter.get_states()
                    for state in states:
                        device_id = state.get("id", "")
                        with self._state_lock:
                            old_state = self._device_states.get(device_id, {})
                            self._device_states[device_id] = state
                        self._report_state(state)
                        if old_state != state and self.on_state_change:
                            self.on_state_change(device_id, state)
                except Exception as e:
                    logger.error(f"State poll failed for {name}: {e}")
            time.sleep(self.poll_interval)

    def _report_state(self, state: Dict[str, Any]):
        if not self.api_url:
            return
        import requests
        payload = {
            "wallet": self.wallet,
            "device_id": state.get("id", ""),
            "device_type": state.get("type", ""),
            "state": state,
            "timestamp": int(time.time()),
        }
        try:
            resp = requests.post(
                f"{self.api_url}/device/state", json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                timeout=10,
            )
            if resp.status_code not in (200, 201, 202):
                logger.warning(f"State report failed: {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"State report error: {e}")

    def send_command(self, device_id: str, command: str, params: Optional[Dict] = None) -> bool:
        params = params or {}
        device_adapter = params.get("_adapter")
        if device_adapter and device_adapter in self._adapters:
            adapter = self._adapters[device_adapter]
            try:
                result = adapter.send_command(device_id, command, params)
                self._report_command(device_id, command, params, result)
                if self.on_command:
                    self.on_command(device_id, command, result)
                return result.get("success", False)
            except Exception as e:
                logger.error(f"Command failed for {device_id}: {e}")
                return False
        for name, adapter in self._adapters.items():
            try:
                result = adapter.send_command(device_id, command, params)
                if result.get("success"):
                    self._report_command(device_id, command, params, result)
                    return True
            except Exception:
                pass
        return False

    def _report_command(self, device_id: str, command: str, params: Dict, result: Dict):
        if not self.api_url:
            return
        import requests
        payload = {
            "wallet": self.wallet,
            "device_id": device_id,
            "command": command,
            "params": params,
            "success": result.get("success", False),
            "result": result,
            "timestamp": int(time.time()),
        }
        try:
            requests.post(
                f"{self.api_url}/device/command", json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                timeout=10,
            )
        except requests.RequestException as e:
            logger.warning(f"Command report error: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_states, daemon=True)
        self._poll_thread.start()
        logger.info("IoT Bridge started")

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        for name, adapter in self._adapters.items():
            try:
                adapter.close()
            except Exception:
                pass
        logger.info("IoT Bridge stopped")

    def run(self):
        self.start()
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
