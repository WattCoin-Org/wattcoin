import json
import sqlite3
from pathlib import Path

from pi.energy_monitor import monitor


def test_read_mock_watts(tmp_path: Path):
    p = tmp_path / "meter.json"
    p.write_text(json.dumps({"watts": 123.4}))
    assert monitor.read_mock_watts(p) == 123.4


def test_persist_reading(tmp_path: Path):
    db = tmp_path / "energy.db"
    conn = monitor.ensure_db(db)
    monitor.persist_reading(conn, "2026-01-01T00:00:00Z", "mock:test", 50.2)

    row = conn.execute("SELECT ts, source, watts FROM readings").fetchone()
    assert row == ("2026-01-01T00:00:00Z", "mock:test", 50.2)


def test_sign_payload_dev_secret(monkeypatch):
    monkeypatch.delenv("WATT_SIGN_CMD", raising=False)
    monkeypatch.setenv("WATT_DEV_SIGNING_SECRET", "abc")

    sig = monitor.sign_payload({"wallet": "x", "value": {"watts": 1}})
    assert isinstance(sig, str)
    assert len(sig) == 64
