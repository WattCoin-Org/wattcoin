#!/usr/bin/env python3
"""Minimal Raspberry Pi sensor oracle scaffold.

Reads two sensor types (DHT22 temp/humidity and PIR motion), writes local history,
signs payloads, and reports to WattCoin oracle API.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SensorSample:
    sensor_type: str
    value: Any
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_type": self.sensor_type,
            "value": self.value,
            "timestamp": self.timestamp,
        }


class MockSensors:
    """Mock sensor source for local development/testing."""

    def __init__(self, mock_file: Path | None = None) -> None:
        self.mock_file = mock_file

    def read_dht22(self) -> list[SensorSample]:
        payload = self._load()
        ts = iso_now()
        return [
            SensorSample("temperature_c", float(payload.get("temperature_c", 23.5)), ts),
            SensorSample("humidity_percent", float(payload.get("humidity_percent", 50.0)), ts),
        ]

    def read_pir(self) -> SensorSample:
        payload = self._load()
        return SensorSample("motion", bool(payload.get("motion", False)), iso_now())

    def _load(self) -> dict[str, Any]:
        if self.mock_file and self.mock_file.exists():
            return json.loads(self.mock_file.read_text(encoding="utf-8"))
        return {}


def build_signature(payload: dict[str, Any], wallet_secret: str) -> str:
    compact = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hmac.new(wallet_secret.encode("utf-8"), compact, hashlib.sha256).hexdigest()


def append_history(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def post_report(api_url: str, payload: dict[str, Any], timeout: float = 8.0) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - known api url input
        return resp.getcode(), resp.read().decode("utf-8", errors="replace")


def collect_and_report(args: argparse.Namespace) -> int:
    sensors = MockSensors(Path(args.mock_file) if args.mock_file else None)

    readings: list[dict[str, Any]] = []
    readings.extend(sample.to_dict() for sample in sensors.read_dht22())
    readings.append(sensors.read_pir().to_dict())

    report = {
        "wallet": args.wallet,
        "timestamp": iso_now(),
        "readings": readings,
    }
    report["signature"] = build_signature(report, args.wallet_secret)

    append_history(Path(args.history_file), report)
    code, text = post_report(args.api_url, report)
    print(f"oracle report status={code} body={text[:200]}")
    return 0 if 200 <= code < 300 else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WattCoin Raspberry Pi sensor oracle")
    p.add_argument("--api-url", default=os.getenv("WATT_ORACLE_API_URL", "http://localhost:5000/api/v1/oracle/report"))
    p.add_argument("--wallet", default=os.getenv("WATT_WALLET", "demo-wallet"))
    p.add_argument("--wallet-secret", default=os.getenv("WATT_WALLET_SECRET", "dev-secret"))
    p.add_argument("--history-file", default=os.getenv("WATT_ORACLE_HISTORY", "pi/sensor_oracle/history.jsonl"))
    p.add_argument("--mock-file", default=os.getenv("WATT_ORACLE_MOCK_FILE", "pi/sensor_oracle/mock_sensors.json"))
    p.add_argument("--interval", type=int, default=int(os.getenv("WATT_ORACLE_INTERVAL_SEC", "60")))
    p.add_argument("--once", action="store_true", help="Send one report and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.once:
        return collect_and_report(args)

    while True:
        rc = collect_and_report(args)
        if rc != 0:
            return rc
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
