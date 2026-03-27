"""
Zigbee2MQTT Adapter — connects to Zigbee2MQTT HTTP API for Zigbee device control.
"""
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("iot-zigbee")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class ZigbeeAdapter:
    """
    Zigbee2MQTT HTTP API Adapter.
    Connects to Zigbee2MQTT REST API to discover and control Zigbee devices.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get("base_url", "http://localhost:8080").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.poll_interval = config.get("poll_interval", 5)
        self.timeout = config.get("timeout", 10)
        self._devices: List[Dict[str, Any]] = []
        self._last_refresh = 0
        if not REQUESTS_AVAILABLE:
            logger.warning("requests not installed. Run: pip install requests")

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Optional[Dict]:
        if not REQUESTS_AVAILABLE:
            return None
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("headers", self._get_headers())
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = requests.request(method, url, **kwargs)
            if resp.status_code in (200, 201):
                return resp.json() if resp.content else {}
            logger.warning(f"Zigbee2MQTT API error: {resp.status_code} {resp.text[:200]}")
        except requests.RequestException as e:
            logger.warning(f"Zigbee2MQTT request failed: {e}")
        return None

    def discover(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/devices")
        if not data or not isinstance(data, list):
            logger.warning("No devices found from Zigbee2MQTT")
            return []
        devices = []
        for item in data:
            ieee = item.get("ieee_address", "")
            definition = item.get("definition", {}) or {}
            device = {
                "id": ieee,
                "name": item.get("friendly_name", ieee),
                "type": definition.get("description", "device"),
                "model": definition.get("model", "Unknown"),
                "vendor": definition.get("vendor", "Unknown"),
                "ieee_address": ieee,
                "status": item.get("status", "offline"),
                "definition": definition,
                "raw": item,
            }
            devices.append(device)
        self._devices = devices
        self._last_refresh = time.time()
        logger.info(f"Discovered {len(devices)} Zigbee devices")
        return devices

    def get_states(self) -> List[Dict[str, Any]]:
        if time.time() - self._last_refresh > self.poll_interval:
            self.discover()
        states = []
        for device in self._devices:
            ieee = device["ieee_address"]
            state_data = self._request("GET", f"/devices/{ieee}")
            if state_data:
                exposable = state_data.get("exposes", []) or []
                state = {
                    "id": ieee, "name": device["name"],
                    "type": device["type"], "status": state_data.get("status", "offline"),
                    "definition": device["definition"], "ieee_address": ieee,
                }
                for item in exposable:
                    if isinstance(item, dict) and item.get("property"):
                        val = state_data.get(item["property"])
                        if val is not None:
                            state[item["property"]] = val
                for key in ["state", "brightness", "temperature", "humidity", "power", "energy"]:
                    if key in state_data:
                        state[key] = state_data[key]
                states.append(state)
        return states

    def send_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        friendly_name = device_id
        for device in self._devices:
            if device["ieee_address"] == device_id or device["id"] == device_id:
                friendly_name = device["name"]
                break
        if command == "on":
            payload = {"state": "ON"}
        elif command == "off":
            payload = {"state": "OFF"}
        elif command == "toggle":
            payload = {"state": "TOGGLE"}
        elif command == "brightness":
            payload = {"brightness": params.get("brightness", 254)}
        elif command == "color_temp":
            payload = {"color_temp": params.get("color_temp", 500)}
        elif command == "temperature":
            payload = {"temperature": params.get("temperature", 2700)}
        else:
            payload = {command: params.get("value", True)}
        result = self._request("POST", f"/devices/{friendly_name}/set", json=payload)
        return {"success": result is not None, "device_id": device_id, "command": command, "response": result}

    def close(self):
        pass
