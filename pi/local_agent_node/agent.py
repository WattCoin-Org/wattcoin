from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


@dataclass
class TaskResult:
    task_id: str
    success: bool
    proof: dict[str, Any]
    earned_watt: int
    error: str | None = None


class LocalAgentNode:
    def __init__(self, api_base: str, node_id: str, db_path: str, mock_mode: bool = False):
        self.api_base = api_base.rstrip("/")
        self.node_id = node_id
        self.mock_mode = mock_mode
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                earned_watt INTEGER NOT NULL,
                proof_json TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def register(self) -> dict[str, Any]:
        payload = {"node_id": self.node_id, "kind": "raspberry-pi-local-agent"}
        if self.mock_mode:
            return {"ok": True, "mock": True, "payload": payload}
        if requests is None:
            raise RuntimeError("requests is required when mock mode is disabled")
        return requests.post(f"{self.api_base}/api/v1/nodes/register", json=payload, timeout=10).json()

    def poll_tasks(self) -> list[dict[str, Any]]:
        if self.mock_mode:
            return [
                {"id": "mock-1", "type": "data_validation", "payload": {"record": {"a": 1, "b": "ok"}}},
                {"id": "mock-2", "type": "file_processing", "payload": {"text": "wattcoin"}},
            ]
        if requests is None:
            raise RuntimeError("requests is required when mock mode is disabled")
        r = requests.get(f"{self.api_base}/api/v1/tasks/available", params={"node_id": self.node_id}, timeout=10)
        return r.json().get("tasks", [])

    def execute_task(self, task: dict[str, Any]) -> TaskResult:
        task_type = task.get("type")
        payload = task.get("payload", {})
        task_id = str(task.get("id", "unknown"))
        try:
            if task_type == "data_validation":
                record = payload.get("record", {})
                valid = isinstance(record, dict) and all(k and v is not None for k, v in record.items())
                proof = {"validated_keys": sorted(record.keys()), "valid": valid}
            elif task_type == "file_processing":
                text = str(payload.get("text", ""))
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                proof = {"sha256": digest, "length": len(text)}
            else:
                return TaskResult(task_id, False, {}, 0, error=f"unsupported task type: {task_type}")
            earned = int(task.get("reward_watt", 1))
            self._save_run(task_id, task_type or "unknown", True, earned, proof)
            return TaskResult(task_id, True, proof, earned)
        except Exception as exc:  # pragma: no cover
            self._save_run(task_id, task_type or "unknown", False, 0, {"error": str(exc)})
            return TaskResult(task_id, False, {}, 0, error=str(exc))

    def report_completion(self, result: TaskResult) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "task_id": result.task_id,
            "success": result.success,
            "proof": result.proof,
            "earned_watt": result.earned_watt,
            "error": result.error,
        }
        if self.mock_mode:
            return {"ok": True, "mock": True, "payload": payload}
        if requests is None:
            raise RuntimeError("requests is required when mock mode is disabled")
        return requests.post(f"{self.api_base}/api/v1/tasks/complete", json=payload, timeout=10).json()

    def _save_run(self, task_id: str, task_type: str, success: bool, earned_watt: int, proof: dict[str, Any]) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO runs (ts, task_id, task_type, success, earned_watt, proof_json) VALUES (?, ?, ?, ?, ?, ?)",
            (int(time.time()), task_id, task_type, int(success), earned_watt, json.dumps(proof, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def stats(self) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(earned_watt), 0), COALESCE(SUM(success), 0) FROM runs"
        ).fetchone()
        conn.close()
        total_tasks, total_earned, successful = row or (0, 0, 0)
        return {
            "node_id": self.node_id,
            "tasks_completed": int(total_tasks),
            "tasks_successful": int(successful),
            "watt_earned": int(total_earned),
            "mock_mode": self.mock_mode,
        }


def from_env() -> LocalAgentNode:
    data_dir = Path(os.getenv("WATT_AGENT_DATA_DIR", "./pi/local_agent_node/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return LocalAgentNode(
        api_base=os.getenv("WATT_API_BASE", "http://127.0.0.1:5000"),
        node_id=os.getenv("WATT_NODE_ID", "pi-local-agent"),
        db_path=str(data_dir / "agent.db"),
        mock_mode=os.getenv("WATT_MOCK_MODE", "1") == "1",
    )


if __name__ == "__main__":
    agent = from_env()
    print(agent.register())
    for task in agent.poll_tasks():
        result = agent.execute_task(task)
        print(agent.report_completion(result))
    print(agent.stats())
