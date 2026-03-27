"""
Mock Adapter — provides mock devices for testing without hardware.
"""
import logging
import random
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger("iot-mock")


class MockAdapter:
    """
    Mock IoT Adapter for testing without real hardware.
    
    Simulates lights, plugs, sensors, and motion detectors.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.devices = config.get("devices", self._default_devices())
        self.fail_rate = config.get("fail_rate", 0.0)
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = True
        for device in self.devices:
            device_id = device.get("id", device.get("name", "unknown"))
            self._states[device_id] = self._init_state(device)

    def _default_devices(self) -> List[Dict[str, Any]]:
        return [
            {"id": "light_1", "type": "light", "name": "Living Room Light"},
            {"id": "light_2", "type": "light", "name": "Bedroom Light"},
            {"id": "plug_1", "type": "plug", "name": "TV Smart Plug"},
            {"id": "plug_2", "type": "plug", "name": "Laptop Plug"},
            {"id": "sensor_1", "type": "sensor", "name": "Living Room Sensor"},
            {"id": "sensor_2", "type": "sensor", "name": "Bedroom Sensor"},
            {"id": "motion_1", "type": "motion", "name": "Hall Motion Sensor"},
        ]

    def _init_state(self, device: Dict[str, Any]) -> Dict[str, Any]:
        device_type = device.get("type", "unknown")
        state = {"id": device.get("id", "unknown"), "name": device.get("name", "Unknown"), "type": device_type, "online": True, "timestamp": time.time()}
        if device_type == "light":
            state.update({"state": "off", "brightness": 0, "color_temp": 400, "reachable": True})
        elif device_type == "plug":
            state.update({"state": "off", "power": 0.0, "voltage": 120.0, "current": 0.0})
        elif device_type == "sensor":
            state.update({"temperature": round(random.uniform(18, 28), 1), "humidity": round(random.uniform(30, 70), 1), "battery": random.randint(50, 100)})
        elif device_type == "motion":
            state.update({"motion": False, "last_motion": time.time() - random.randint(60, 3600), "battery": random.randint(50, 100)})
        return state

    def discover(self) -> List[Dict[str, Any]]:
        return [{"id": d.get("id", "unknown"), "name": d.get("name", "Unknown"), "type": d.get("type", "unknown"), "online": True} for d in self.devices]

    def get_states(self) -> List[Dict[str, Any]]:
        with self._lock:
            for device in self.devices:
                device_id = device.get("id", "unknown")
                if device_id not in self._states:
                    continue
                state = self._states[device_id]
                device_type = device.get("type", "unknown")
                if device_type == "sensor" and random.random() < 0.3:
                    state["temperature"] = round(random.uniform(18, 28), 1)
                    state["humidity"] = round(random.uniform(30, 70), 1)
                    state["timestamp"] = time.time()
                elif device_type == "motion":
                    if random.random() < 0.1:
                        state["motion"] = True
                        state["last_motion"] = time.time()
                    elif random.random() < 0.3:
                        state["motion"] = False
                elif device_type == "plug" and random.random() < 0.05:
                    current = state.get("state", "off")
                    state["state"] = "on" if current == "off" else "off"
                    state["power"] = random.uniform(5, 150) if state["state"] == "on" else 0.0
                    state["timestamp"] = time.time()
                elif device_type == "light" and random.random() < 0.05:
                    current = state.get("state", "off")
                    state["state"] = "on" if current == "off" else "off"
                    state["brightness"] = random.randint(50, 254) if state["state"] == "on" else 0
                    state["timestamp"] = time.time()
            return [dict(s) for s in self._states.values()]

    def send_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        if random.random() < self.fail_rate:
            return {"success": False, "error": "Simulated failure", "device_id": device_id}
        with self._lock:
            if device_id not in self._states:
                return {"success": False, "error": f"Unknown device: {device_id}"}
            state = self._states[device_id]
            device_type = state.get("type", "")
            if command == "on":
                state["state"] = "on"
                if device_type == "light":
                    state["brightness"] = params.get("brightness", 254)
                elif device_type == "plug":
                    state["power"] = random.uniform(5, 150)
                state["timestamp"] = time.time()
            elif command == "off":
                state["state"] = "off"
                if device_type == "light":
                    state["brightness"] = 0
                elif device_type == "plug":
                    state["power"] = 0.0
                state["timestamp"] = time.time()
            elif command == "toggle":
                current = state.get("state", "off")
                state["state"] = "off" if current == "on" else "on"
                if device_type == "light":
                    state["brightness"] = random.randint(50, 254) if state["state"] == "on" else 0
                elif device_type == "plug":
                    state["power"] = random.uniform(5, 150) if state["state"] == "on" else 0.0
                state["timestamp"] = time.time()
            elif command == "brightness" and device_type == "light":
                brightness = params.get("brightness", 254)
                state["brightness"] = max(1, min(254, brightness))
                state["state"] = "on" if brightness > 0 else "off"
                state["timestamp"] = time.time()
            elif command == "color_temp" and device_type == "light":
                state["color_temp"] = max(153, min(500, params.get("color_temp", 400)))
                state["timestamp"] = time.time()
            return {"success": True, "device_id": device_id, "command": command, "state": dict(state)}

    def close(self):
        self._running = False
