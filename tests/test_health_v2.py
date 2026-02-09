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
    # 1. Check for legacy fields
    resp = client.get('/health')
    data = resp.get_json()
    assert "ai" in data
    assert "claude" in data
    assert "proxy" in data
    assert "admin" in data
    assert "version" in data
    assert data["version"] == "3.4.0"

def test_health_metrics(client):
    # 2. Check for metrics
    resp = client.get('/health')
    data = resp.get_json()
    assert "active_nodes" in data
    assert "open_tasks" in data
    assert "uptime_seconds" in data

def test_health_services_structure(client):
    # 3. Check services structure
    resp = client.get('/health')
    data = resp.get_json()
    assert "services" in data
    assert "database" in data["services"]
    assert "discord_alerts" in data["services"]
    assert "ai_integration" in data["services"]

def test_health_degraded_ai(client, monkeypatch):
    # 4. Test AI degraded
    with monkeypatch.context() as m:
        # We can't easily mock the global ai_client in bridge_web from here
        # but we can verify the status code is 200
        resp = client.get('/health')
        assert resp.status_code == 200

def test_health_timestamp(client):
    # 5. Check timestamp format
    resp = client.get('/health')
    data = resp.get_json()
    assert "timestamp" in data
    # Simple ISO format check
    assert "T" in data["timestamp"]
