import json

from pi.iot_bridge.bridge import BridgeConfig, IoTBridge, MockMQTTAdapter, MockZigbeeAdapter
from pi.iot_bridge.config_ui import app


def test_collect_states_supports_two_protocols():
    bridge = IoTBridge(
        config=BridgeConfig(api_base_url="http://localhost:8000", mock_mode=True),
        adapters=[MockMQTTAdapter(), MockZigbeeAdapter()],
    )
    events = bridge.collect_states()
    protocols = {event["protocol"] for event in events}
    assert protocols == {"mqtt", "zigbee2mqtt"}


def test_report_states_mock_mode():
    bridge = IoTBridge(
        config=BridgeConfig(api_base_url="http://localhost:8000", mock_mode=True),
        adapters=[MockMQTTAdapter(), MockZigbeeAdapter()],
    )
    result = bridge.report_states(bridge.collect_states())
    assert result["ok"] is True
    assert result["mock"] is True


def test_command_relay_functional():
    bridge = IoTBridge(
        config=BridgeConfig(api_base_url="http://localhost:8000", mock_mode=True),
        adapters=[MockMQTTAdapter(), MockZigbeeAdapter()],
    )
    result = bridge.relay_command({"protocol": "mqtt", "action": "toggle"})
    assert result["ok"] is True
    assert result["result"]["ack"] is True


def test_config_ui_get_and_update():
    client = app.test_client()
    get_resp = client.get("/config")
    assert get_resp.status_code == 200

    post_resp = client.post(
        "/config",
        data=json.dumps({"api_base_url": "https://api.example.com"}),
        content_type="application/json",
    )
    assert post_resp.status_code == 200
    assert post_resp.get_json()["config"]["api_base_url"] == "https://api.example.com"
