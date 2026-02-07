import api_tasks
import bridge_web


def test_leaderboard_default_sort_by_earned(monkeypatch):
    sample = {
        "tasks": {
            "t1": {
                "status": "verified",
                "claimer_wallet": "11111111AAAAAAAA",
                "claimer_name": "ClawBot",
                "worker_payout": 1000,
                "verification": {"score": 8},
            },
            "t2": {
                "status": "verified",
                "claimer_wallet": "11111111AAAAAAAA",
                "claimer_name": "ClawBot",
                "worker_payout": 500,
                "verification": {"score": 6},
            },
            "t3": {
                "status": "verified",
                "claimer_wallet": "22222222BBBBBBBB",
                "claimer_name": "AgentB",
                "worker_payout": 2000,
                "verification": {"score": 9},
            },
            "t4": {
                "status": "open",
                "claimer_wallet": "33333333CCCCCCCC",
                "claimer_name": "Nope",
                "worker_payout": 9999,
                "verification": {"score": 10},
            },
        },
        "stats": {},
    }
    monkeypatch.setattr(api_tasks, "load_tasks", lambda: sample)

    client = bridge_web.app.test_client()
    resp = client.get("/api/v1/tasks/leaderboard")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    lb = data["leaderboard"]
    assert lb[0]["rank"] == 1
    assert lb[0]["wallet"] == "22222222..."
    assert lb[0]["total_earned"] == 2000
    assert lb[0]["tasks_completed"] == 1
    assert lb[0]["avg_score"] == 9.0


def test_leaderboard_sort_by_completed(monkeypatch):
    sample = {
        "tasks": {
            "t1": {
                "status": "verified",
                "claimer_wallet": "11111111AAAAAAAA",
                "claimer_name": "ClawBot",
                "worker_payout": 1000,
                "verification": {"score": 8},
            },
            "t2": {
                "status": "verified",
                "claimer_wallet": "11111111AAAAAAAA",
                "claimer_name": "ClawBot",
                "worker_payout": 500,
                "verification": {"score": 6},
            },
            "t3": {
                "status": "verified",
                "claimer_wallet": "22222222BBBBBBBB",
                "claimer_name": "AgentB",
                "worker_payout": 2000,
                "verification": {"score": 9},
            },
        },
        "stats": {},
    }
    monkeypatch.setattr(api_tasks, "load_tasks", lambda: sample)

    client = bridge_web.app.test_client()
    resp = client.get("/api/v1/tasks/leaderboard?sort_by=completed&limit=20")
    assert resp.status_code == 200
    lb = resp.get_json()["leaderboard"]
    assert lb[0]["wallet"] == "11111111..."
    assert lb[0]["tasks_completed"] == 2
