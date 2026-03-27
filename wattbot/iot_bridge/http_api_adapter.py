"""
HTTP API Adapter — connects to direct device APIs (Kasa Smart Plug, Philips Hue, etc.)
"""
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("iot-http")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class HttpApiAdapter:
    """
    HTTP API Adapter for direct device communication.
    
    Supports:
    - Kasa Smart Plugs/Switches (TP-Link)
    - Philips Hue Bridges
    - Generic HTTP API devices
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.device_type = config.get("type", "http").lower()
        self.devices = config.get("devices", [])
        self.timeout = config.get("timeout", 10)
        self._api_key: Optional[str] = None
        self._hue_bridge_ip: Optional[str] = None
        if self.device_type == "hue":
            self._init_hue(config)
        if not REQUESTS_AVAILABLE:
            logger.warning("requests not installed. Run: pip install requests")

    def _init_hue(self, config: Dict[str, Any]):
        self._hue_bridge_ip = config.get("bridge_ip")
        self._api_key = config.get("api_key")
        if not self._api_key and self._hue_bridge_ip:
            try:
                resp = requests.post(
                    f"http://{self._hue_bridge_ip}/api",
                    json={"devicetype": "wattcoin_iot#bridge"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and "success" in data[0]:
                        self._api_key = data[0]["success"]["username"]
                        logger.info("Hue API key discovered")
            except Exception as e:
                logger.warning(f"Hue API key discovery failed: {e}")

    def discover(self) -> List[Dict[str, Any]]:
        if self.device_type == "hue":
            return self._discover_hue()
        elif self.device_type == "kasa":
            return self._discover_kasa()
        elif self.devices:
            return self._discover_generic()
        return []

    def _discover_hue(self) -> List[Dict[str, Any]]:
        if not REQUESTS_AVAILABLE or not self._hue_bridge_ip or not self._api_key:
            return []
        try:
            resp = requests.get(f"http://{self._hue_bridge_ip}/api/{self._api_key}/lights", timeout=self.timeout)
            if resp.status_code == 200:
                lights = resp.json()
                devices = []
                for light_id, light_data in lights.items():
                    devices.append({
                        "id": f"hue_{light_id}",
                        "name": light_data.get("name", f"Hue Light {light_id}"),
                        "type": "light", "model": light_data.get("modelid", ""),
                        "hue_id": light_id, "state": light_data.get("state", {}),
                    })
                logger.info(f"Discovered {len(devices)} Hue lights")
                return devices
        except Exception as e:
            logger.warning(f"Hue discovery failed: {e}")
        return []

    def _discover_kasa(self) -> List[Dict[str, Any]]:
        devices = []
        for dc in self.devices:
            host = dc.get("host")
            if not host:
                continue
            state = self._get_kasa_state(host, dc.get("port", 9999))
            if state:
                state["id"] = f"kasa_{host}"
                state["name"] = dc.get("name", f"Kasa {host}")
                state["host"] = host
                devices.append(state)
        return devices

    def _discover_generic(self) -> List[Dict[str, Any]]:
        devices = []
        for dc in self.devices:
            device_id = dc.get("id", dc.get("url", "unknown"))
            url = dc.get("url")
            name = dc.get("name", device_id)
            if not url:
                continue
            try:
                resp = requests.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
                    devices.append({"id": device_id, "name": name, "type": dc.get("type", "device"), "url": url, "state": data})
            except Exception as e:
                logger.warning(f"Generic device {device_id} unreachable: {e}")
        return devices

    def _get_kasa_state(self, host: str, port: int = 9999) -> Optional[Dict[str, Any]]:
        try:
            import socket
            import json
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.send(b'{"system":{"get_sysinfo":{}}}')
            data = sock.recv(4096)
            sock.close()
            info = json.loads(data.decode("utf-8", errors="replace"))
            sys_info = info.get("system", {}).get("get_sysinfo", {})
            return {
                "type": "smartplug", "model": sys_info.get("model", "Unknown"),
                "alias": sys_info.get("alias", host), "device_id": sys_info.get("deviceId", ""),
                "state": sys_info.get("relay_state", 0), "on": bool(sys_info.get("relay_state", 0)),
            }
        except Exception:
            return None

    def get_states(self) -> List[Dict[str, Any]]:
        return self.discover()

    def send_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        if device_id.startswith("hue_"):
            return self._hue_command(device_id, command, params)
        elif device_id.startswith("kasa_"):
            return self._kasa_command(device_id, command, params)
        else:
            return self._generic_command(device_id, command, params)

    def _hue_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        light_id = device_id.replace("hue_", "")
        if not REQUESTS_AVAILABLE or not self._hue_bridge_ip or not self._api_key:
            return {"success": False, "error": "Hue not configured"}
        payload = {}
        if command == "on":
            payload["on"] = True
        elif command == "off":
            payload["on"] = False
        elif command == "brightness":
            brightness = params.get("brightness", 254)
            payload["on"] = True
            payload["bri"] = max(1, min(254, int(brightness)))
        elif command == "color_temp":
            payload["ct"] = params.get("color_temp", 500)
        try:
            resp = requests.put(
                f"http://{self._hue_bridge_ip}/api/{self._api_key}/lights/{light_id}/state",
                json=payload, timeout=self.timeout,
            )
            return {"success": resp.status_code in (200, 201), "response": resp.json() if resp.content else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _kasa_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        host = device_id.replace("kasa_", "")
        try:
            import socket
            import json
            port = 9999
            for dc in self.devices:
                if dc.get("host") == host:
                    port = dc.get("port", 9999)
                    break
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            if command == "on":
                cmd = {"system": {"set_relay_state": {"state": 1}}}
            elif command == "off":
                cmd = {"system": {"set_relay_state": {"state": 0}}}
            else:
                cmd = {"system": {"set_relay_state": {"state": 0}}}
            sock.send(json.dumps(cmd).encode())
            data = sock.recv(4096)
            sock.close()
            result = json.loads(data.decode("utf-8", errors="replace"))
            success = result.get("system", {}).get("set_relay_state", {}).get("err_code", 1) == 0
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generic_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        for dc in self.devices:
            if dc.get("id") == device_id:
                url = dc.get("url")
                if not url:
                    break
                method = dc.get("method", "POST").upper()
                cmd_url = dc.get(f"cmd_{command}_url", url)
                try:
                    resp = requests.request(method, cmd_url, json=params, timeout=self.timeout)
                    return {"success": resp.status_code in (200, 201, 202)}
                except Exception as e:
                    return {"success": False, "error": str(e)}
        return {"success": False, "error": "Device not found"}

    def close(self):
        pass
