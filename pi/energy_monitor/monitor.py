#!/usr/bin/env python3
"""Raspberry Pi energy monitor scaffold for WattCoin bounty #15.

Supports:
- Kasa smart plugs (python-kasa, optional)
- Mock/USB meter JSON file input

Reports to /api/v1/energy/report with a signature produced by an external signer
command so private keys stay outside this process.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import subprocess
import time
from typing import Any, Dict, Optional

import requests


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_mock_watts(path: pathlib.Path) -> float:
    payload = json.loads(path.read_text())
    return float(payload["watts"])


def read_kasa_watts(host: str) -> float:
    try:
        from kasa import SmartPlug  # type: ignore
        import asyncio
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("python-kasa not installed; pip install python-kasa") from exc

    async def _read() -> float:
        plug = SmartPlug(host)
        await plug.update()
        return float(plug.emeter_realtime.power)

    return float(asyncio.run(_read()))


def ensure_db(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            source TEXT NOT NULL,
            watts REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def persist_reading(conn: sqlite3.Connection, ts: str, source: str, watts: float) -> None:
    conn.execute("INSERT INTO readings(ts, source, watts) VALUES (?, ?, ?)", (ts, source, watts))
    conn.commit()


def sign_payload(payload: Dict[str, Any]) -> str:
    sign_cmd = os.getenv("WATT_SIGN_CMD", "").strip()
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    # Preferred: external signer command, e.g. `solana-keygen sign --keypair ...`
    if sign_cmd:
        proc = subprocess.run(
            sign_cmd,
            shell=True,
            input=body,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"sign command failed: {proc.stderr.strip()}")
        sig = proc.stdout.strip()
        if not sig:
            raise RuntimeError("sign command returned empty signature")
        return sig

    # Dev fallback for local testing only.
    dev_secret = os.getenv("WATT_DEV_SIGNING_SECRET", "")
    if dev_secret:
        return hmac.new(dev_secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    raise RuntimeError("No signer configured. Set WATT_SIGN_CMD (preferred) or WATT_DEV_SIGNING_SECRET (dev only).")


def post_report(base_url: str, report: Dict[str, Any], timeout_s: int) -> Dict[str, Any]:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/v1/energy/report",
        json=report,
        timeout=timeout_s,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else {"ok": True}


def collect_once(args: argparse.Namespace, conn: sqlite3.Connection) -> Dict[str, Any]:
    ts = utc_now()
    if args.source == "kasa":
        watts = read_kasa_watts(args.kasa_host)
        source_meta = f"kasa:{args.kasa_host}"
    else:
        watts = read_mock_watts(pathlib.Path(args.mock_file))
        source_meta = f"mock:{args.mock_file}"

    persist_reading(conn, ts, source_meta, watts)

    payload = {
        "wallet": args.wallet,
        "timestamp": ts,
        "source": args.source,
        "value": {"watts": watts},
        "unit": "W",
    }
    payload["signature"] = sign_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Pi energy monitor reporter")
    parser.add_argument("--base-url", required=True, help="WattCoin API base URL")
    parser.add_argument("--wallet", required=True, help="Wallet address")
    parser.add_argument("--db", default="energy_monitor.db")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--source", choices=["kasa", "mock"], default="mock")
    parser.add_argument("--kasa-host", default="")
    parser.add_argument("--mock-file", default="mock_meter.json")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    conn = ensure_db(pathlib.Path(args.db))

    while True:
        report = collect_once(args, conn)
        result = post_report(args.base_url, report, args.timeout)
        print(json.dumps({"sent": report, "result": result}, ensure_ascii=False))

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
