"""
MQTT Adapter — connects to MQTT brokers for smart home device state and control.
"""
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("iot-mqtt")

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


class MQTTAdapter:
    """
    MQTT Adapter for connecting to smart home devices via MQTT broker.
    
    Supports Home Assistant MQTT, Zigbee2MQTT, Tasmota, ESPHome, Shelly, etc.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.broker = config.get("broker", "localhost")
        self.port = config.get("port", 1883)
        self.username = config.get("username")
        self.password = config.get("password")
        self.topics = config.get("topics", ["#"])
        self.topic_prefix = config.get("topic_prefix", "")
        self.qos = config.get("qos", 1)
        
        self._client: Optional[Any] = None
        self._connected = False
        self._lock = threading.Lock()
        self._messages: Dict[str, Any] = {}
        self._conn_event = threading.Event()
        
        if not MQTT_AVAILABLE:
            logger.warning("paho-mqtt not installed. Run: pip install paho-mqtt")
        else:
            self._connect()

    def _connect(self):
        if not MQTT_AVAILABLE:
            return
        client_id = f"wattcoin_iot_{int(time.time())}"
        self._client = mqtt.Client(client_id=client_id)
        if self.username:
            self._client.username_pw_set(self.username, self.password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        try:
            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            self._conn_event.set()
            logger.info(f"Connected to MQTT broker {self.broker}:{self.port}")
            for topic in self.topics:
                full = f"{self.topic_prefix}/{topic}".replace("//", "/") if self.topic_prefix else topic
                self._client.subscribe(full, qos=self.qos)
                logger.info(f"Subscribed to {full}")
        else:
            logger.warning(f"MQTT connect failed with rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        self._conn_event.clear()
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")
        time.sleep(5)
        try:
            self._client.reconnect()
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8", errors="replace")
            try:
                data = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                data = {"raw": payload}
            with self._lock:
                self._messages[topic] = {"topic": topic, "payload": data, "timestamp": time.time()}
        except Exception as e:
            logger.debug(f"Message parse error: {e}")

    def discover(self) -> List[Dict[str, Any]]:
        devices = []
        if not self._connected:
            logger.warning("Not connected to MQTT broker")
            return devices
        with self._lock:
            for topic, msg_data in self._messages.items():
                if any(skip in topic.lower() for skip in ["tele/", "stat/", "homeassistant"]):
                    continue
                device = self._parse_device(topic, msg_data.get("payload", {}))
                if device:
                    devices.append(device)
        return devices

    def _parse_device(self, topic: str, payload: Any) -> Optional[Dict[str, Any]]:
        if isinstance(payload, dict):
            state = payload.get("state", payload.get("brightness", "unknown"))
            name = payload.get("device_name") or payload.get("friendly_name") or topic.split("/")[-1]
            return {
                "id": topic.replace("/", "_"),
                "name": str(name),
                "type": self._infer_type(payload),
                "topic": topic,
                "state": state,
                "raw": payload,
            }
        return None

    def _infer_type(self, payload: Dict) -> str:
        if "temperature" in payload or "humidity" in payload:
            return "sensor"
        if "brightness" in payload or "color_temp" in payload:
            return "light"
        if "power" in payload:
            return "switch"
        if "position" in payload:
            return "cover"
        return "unknown"

    def get_states(self) -> List[Dict[str, Any]]:
        states = []
        with self._lock:
            for topic, msg_data in self._messages.items():
                payload = msg_data.get("payload", {})
                if isinstance(payload, dict):
                    states.append({
                        "id": topic.replace("/", "_"),
                        "topic": topic,
                        "state": payload.get("state", "unknown"),
                        "raw": payload,
                        "timestamp": msg_data.get("timestamp"),
                    })
        return states

    def send_command(self, device_id: str, command: str, params: Dict) -> Dict[str, Any]:
        if not self._connected:
            return {"success": False, "error": "Not connected"}
        topic = device_id.replace("_", "/")
        if command == "on":
            payload = "ON"
        elif command == "off":
            payload = "OFF"
        elif command == "toggle":
            payload = "TOGGLE"
        elif command == "brightness":
            payload = str(params.get("brightness", 255))
        else:
            payload = json.dumps(params)
        result = self._client.publish(topic, payload, qos=self.qos)
        return {"success": result.rc == mqtt.MQTT_ERR_SUCCESS}

    def close(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
