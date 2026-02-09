import pytest
import os
from bridge_web import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint_format(client, monkeypatch):
    """Test health endpoint returns expected fields."""
    monkeypatch.setenv("AI_API_KEY", "test_key")
    # Mock data dir to current dir to ensure files aren't found (testing degraded/healthy logic)
    monkeypatch.setenv("DATA_DIR", ".") 
    
    resp = client.get('/health')
    data = resp.get_json()
    
    # Check for legacy fields
    assert "ai" in data
    assert "claude" in data
    assert "proxy" in data
    assert "admin" in data
    assert data["status"] in ["ok", "degraded"]
    
    # Check for new fields
    assert "services" in data
    assert "database" in data["services"]
    assert "active_nodes" in data
    assert "open_tasks" in data
    assert "timestamp" in data

def test_health_degraded_status(client, monkeypatch):
    """Test status field shows degraded when critical service is missing (HTTP still 200)."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "degraded"
