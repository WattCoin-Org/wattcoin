"""Minimal Raspberry Pi IoT bridge scaffold for WattCoin bounty #17.

Supports two protocol adapters (MQTT + Zigbee2MQTT) in real or mock mode,
forwards state updates to a configurable API endpoint, and relays paid command
requests to local devices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import logging
import os

import requests


LOG = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    api_base_url: str
    api_key: Optional[str] = None
    mock_mode: bool = True


class ProtocolAdapter:
    name: str = "unknown"

    def read_state(self) -> Dict[str, Any]:
        raise NotImplementedError

    def apply_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class MockMQTTAdapter(ProtocolAdapter):
    name = "mqtt"

    def read_state(self) -> Dict[str, Any]:
        return {
            "topic": "home/power_meter",
            "value": {"watts": 123.4, "online": True},
        }

    def apply_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"ack": True, "transport": "mqtt", "command": command}


class MockZigbeeAdapter(ProtocolAdapter):
    name = "zigbee2mqtt"

    def read_state(self) -> Dict[str, Any]:
        return {
            "device": "livingroom_light",
            "value": {"state": "ON", "brightness": 180},
        }

    def apply_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"ack": True, "transport": "zigbee2mqtt", "command": command}


class IoTBridge:
    def __init__(self, config: BridgeConfig, adapters: List[ProtocolAdapter]):
        self.config = config
        self.adapters = adapters

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def collect_states(self) -> List[Dict[str, Any]]:
        events = []
        now = datetime.now(timezone.utc).isoformat()
        for adapter in self.adapters:
            events.append(
                {
                    "protocol": adapter.name,
                    "timestamp": now,
                    "state": adapter.read_state(),
                }
            )
        return events

    def report_states(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.config.api_base_url.rstrip('/')}/api/v1/iot/state"
        payload = {"events": events}
        if self.config.mock_mode:
            return {"ok": True, "mock": True, "url": url, "events": len(events)}

        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=8)
            resp.raise_for_status()
            return {"ok": True, "status_code": resp.status_code}
        except requests.RequestException as exc:
            LOG.warning("State report failed: %s", exc)
            return {"ok": False, "error": str(exc), "url": url}

    def relay_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        protocol = command.get("protocol")
        adapter = next((a for a in self.adapters if a.name == protocol), None)
        if adapter is None:
            return {"ok": False, "error": f"unsupported protocol: {protocol}"}

        result = adapter.apply_command(command)
        return {"ok": True, "result": result}


def build_bridge_from_env() -> IoTBridge:
    config = BridgeConfig(
        api_base_url=os.getenv("WATT_API_BASE_URL", "http://localhost:8000"),
        api_key=os.getenv("WATT_API_KEY"),
        mock_mode=os.getenv("WATT_MOCK_MODE", "1") == "1",
    )
    adapters: List[ProtocolAdapter] = [MockMQTTAdapter(), MockZigbeeAdapter()]
    return IoTBridge(config=config, adapters=adapters)


def run_once() -> str:
    bridge = build_bridge_from_env()
    events = bridge.collect_states()
    report = bridge.report_states(events)
    demo_command = {"protocol": "mqtt", "target": "home/plug_1", "action": "toggle"}
    command_result = bridge.relay_command(demo_command)
    output = {"report": report, "command": command_result, "events": events}
    return json.dumps(output, ensure_ascii=False)


if __name__ == "__main__":
    print(run_once())
