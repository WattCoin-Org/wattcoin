import bridge_web


def _run_health(monkeypatch, exists, webhook, ai_key, nodes, tasks):
    monkeypatch.setattr(bridge_web.os, "getenv", lambda k, d=None: {
        "DATA_DIR": "/tmp/data", "DISCORD_WEBHOOK": webhook, "AI_API_KEY": ai_key
    }.get(k, d))
    monkeypatch.setattr(bridge_web.os.path, "exists", lambda _p: exists)
    monkeypatch.setattr(bridge_web.os, "access", lambda _p, _m: exists)
    monkeypatch.setattr(bridge_web, "get_active_nodes", lambda: nodes)
    monkeypatch.setattr(bridge_web, "load_tasks", lambda: tasks)
    resp = bridge_web.app.test_client().get("/health")
    return resp.get_json(), resp.status_code


def test_health_healthy(monkeypatch):
    data, code = _run_health(monkeypatch, True, "https://discord.test/webhook", "key", ["n1", "n2"], [{"status": "open"}, {"status": "claimed"}])
    assert code == 200 and data["status"] == "healthy"
    assert data["services"] == {"data_files": "ok", "discord": "ok", "ai_api": "ok"}
    assert data["active_nodes"] == 2 and data["open_tasks"] == 1


def test_health_degraded(monkeypatch):
    data, code = _run_health(monkeypatch, False, "", "", [], [])
    assert code == 503 and data["status"] == "degraded"
    assert data["services"] == {"data_files": "degraded", "discord": "degraded", "ai_api": "degraded"}
    assert data["active_nodes"] == 0 and data["open_tasks"] == 0
