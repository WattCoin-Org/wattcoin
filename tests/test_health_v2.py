import pytest
import os
import json
from bridge_web import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint_format(client, monkeypatch):
    # 1. Check for legacy fields and correct version
    resp = client.get('/health')
    data = resp.get_json()
    assert "status" in data
    assert data["status"] == "ok" # Must always be ok for legacy systems
    assert "ai" in data
    assert "claude" in data
    assert "proxy" in data
    assert "admin" in data
    assert "version" in data
    assert data["version"] == "3.4.0"

def test_health_degraded_state(client, monkeypatch):
    # 2. Test degraded state detection (mocking DATA_DIR to non-existent)
    with monkeypatch.context() as m:
        m.setenv("DATA_DIR", "/tmp/non_existent_dir_wattcoin")
        resp = client.get('/health')
        data = resp.get_json()
        assert data["status"] == "ok" # Status remains 'ok'
        assert data["health_status"] == "degraded"
        assert data["services"]["database"] == "error"

def test_health_services_structure(client):
    # 3. Check services structure and naming
    resp = client.get('/health')
    data = resp.get_json()
    assert "services" in data
    assert "database" in data["services"]
    assert "discord_alerts" in data["services"]
    assert "ai_integration" in data["services"]

def test_health_uptime_tracking(client):
    # 4. Check uptime metric
    resp = client.get('/health')
    data = resp.get_json()
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0

def test_health_network_metrics(client):
    # 5. Check active node counting
    resp = client.get('/health')
    data = resp.get_json()
    assert "active_nodes" in data
    assert "open_tasks" in data
    assert isinstance(data["active_nodes"], int)

def test_health_timestamp(client):
    # 6. Check timestamp format
    resp = client.get('/health')
    data = resp.get_json()
    assert "timestamp" in data
    # Simple ISO format check
    assert "T" in data["timestamp"]
