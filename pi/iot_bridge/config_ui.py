"""Local config UI for Raspberry Pi IoT bridge (Flask)."""

from __future__ import annotations

from flask import Flask, jsonify, request


app = Flask(__name__)


CONFIG = {
    "api_base_url": "http://localhost:8000",
    "device_mappings": [
        {"protocol": "mqtt", "source": "home/power_meter", "asset": "meter-1"},
        {"protocol": "zigbee2mqtt", "source": "livingroom_light", "asset": "light-1"},
    ],
}


@app.get("/config")
def get_config():
    return jsonify(CONFIG)


@app.post("/config")
def update_config():
    payload = request.get_json(silent=True) or {}
    if "api_base_url" in payload:
        CONFIG["api_base_url"] = payload["api_base_url"]
    if "device_mappings" in payload and isinstance(payload["device_mappings"], list):
        CONFIG["device_mappings"] = payload["device_mappings"]
    return jsonify({"ok": True, "config": CONFIG})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787)
