import bridge_web


def test_health_healthy(monkeypatch):
    client = bridge_web.app.test_client()

    monkeypatch.setattr(bridge_web.os, "getenv", lambda k, d=None: {
        "DATA_DIR": "/tmp/data",
        "DISCORD_WEBHOOK": "https://discord.test/webhook",
        "AI_API_KEY": "key",
    }.get(k, d))
    monkeypatch.setattr(bridge_web.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(bridge_web.os, "access", lambda _p, _m: True)
    monkeypatch.setattr(bridge_web, "get_active_nodes", lambda: ["n1", "n2"])
    monkeypatch.setattr(bridge_web, "load_tasks", lambda: [{"status": "open"}, {"status": "claimed"}])

    response = client.get("/health")
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == "healthy"
    assert data["services"]["data_files"] == "ok"
    assert data["services"]["discord"] == "ok"
    assert data["services"]["ai_api"] == "ok"
    assert data["active_nodes"] == 2
    assert data["open_tasks"] == 1


def test_health_degraded(monkeypatch):
    client = bridge_web.app.test_client()

    monkeypatch.setattr(bridge_web.os, "getenv", lambda k, d=None: {
        "DATA_DIR": "/tmp/data",
        "DISCORD_WEBHOOK": "",
        "AI_API_KEY": "",
    }.get(k, d))
    monkeypatch.setattr(bridge_web.os.path, "exists", lambda _p: False)
    monkeypatch.setattr(bridge_web.os, "access", lambda _p, _m: False)
    monkeypatch.setattr(bridge_web, "get_active_nodes", lambda: [])
    monkeypatch.setattr(bridge_web, "load_tasks", lambda: [])

    response = client.get("/health")
    data = response.get_json()

    assert response.status_code == 503
    assert data["status"] == "degraded"
    assert data["services"]["data_files"] == "degraded"
    assert data["services"]["discord"] == "degraded"
    assert data["services"]["ai_api"] == "degraded"
    assert data["active_nodes"] == 0
    assert data["open_tasks"] == 0
