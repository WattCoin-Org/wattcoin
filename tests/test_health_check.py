import json
import os
import time
import bridge_web

def test_health_check_healthy(monkeypatch):
    """Test health check returns 200 when critical services are ok."""
    # Mock files as readable
    monkeypatch.setattr(os, "access", lambda path, mode: True)
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    
    # Mock tasks.json content
    mock_tasks = {
        "tasks": {
            "t1": {"status": "open"},
            "t2": {"status": "claimed"},
            "t3": {"status": "open"}
        }
    }
    
    # Using a simpler way to mock json.load for the health function's context
    def mock_json_load(f):
        return mock_tasks
    
    monkeypatch.setattr(json, "load", mock_json_load)
    
    # Mock open() to avoid actual file access
    class MockFile:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    # Need to be careful with builtins.open as it can break things
    # Instead, we just mock the logic inside the try-except block
    
    # Mock node count
    monkeypatch.setattr(bridge_web, "get_active_nodes", lambda: [1, 2, 3])
    
    # Mock env
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123")
    # Mock ai_client directly in the module
    monkeypatch.setattr(bridge_web, "ai_client", True)
    
    client = bridge_web.app.test_client()
    
    # Ensure start time is set
    bridge_web.app._server_start_time = time.time() - 100
    
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["active_nodes"] == 3
    assert data["open_tasks"] == 2
    assert data["services"]["database"] == "ok"
    assert data["services"]["discord"] == "ok"
    assert data["uptime_seconds"] >= 100

def test_health_check_degraded(monkeypatch):
    """Test health check returns 503 when critical service (database/api keys) is unreadable."""
    # Mock api_keys.json as unreadable
    def mock_access(path, mode):
        if "api_keys.json" in path:
            return False
        return True
    
    monkeypatch.setattr(os, "access", mock_access)
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    monkeypatch.setattr(json, "load", lambda f: {"tasks": {}})
    
    client = bridge_web.app.test_client()
    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.get_json()
    assert data["status"] == "degraded"
    assert data["services"]["database"] == "error"
