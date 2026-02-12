from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(slots=True)
class RelayConfig:
    api_base: str = "http://127.0.0.1:5001"
    relay_id: str = ""
    relay_secret: str = ""
    model: str = "tinyllama"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "RelayConfig":
        relay_id = os.getenv("WATT_RELAY_ID", "").strip()
        if not relay_id:
            relay_id = f"pi-relay-{uuid.uuid4().hex[:8]}"

        relay_secret = os.getenv("WATT_RELAY_SECRET", "").strip() or "dev-secret"
        return cls(
            api_base=os.getenv("WATT_API_BASE", "http://127.0.0.1:5001").rstrip("/"),
            relay_id=relay_id,
            relay_secret=relay_secret,
            model=os.getenv("WATT_RELAY_MODEL", "tinyllama").strip() or "tinyllama",
            timeout_seconds=int(os.getenv("WATT_RELAY_TIMEOUT", "30")),
        )


class InferenceRelay:
    def __init__(self, config: RelayConfig):
        self.config = config

    def _signed_headers(self, body: dict[str, Any]) -> dict[str, str]:
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        sig = hmac.new(self.config.relay_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Relay-Id": self.config.relay_id,
            "X-Relay-Signature": sig,
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.config.api_base}{path}",
            data=body,
            method="POST",
            headers=self._signed_headers(payload),
        )
        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} on {path}: {detail}") from exc

    def _mock_infer(self, prompt: str) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return ""
        return f"[{self.config.model}] {prompt[:180]}"

    def run_once(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id") or uuid.uuid4().hex)
        prompt = str(job.get("prompt") or "")
        started = time.time()

        output = self._mock_infer(prompt)

        result = {
            "job_id": job_id,
            "relay_id": self.config.relay_id,
            "model": self.config.model,
            "latency_ms": int((time.time() - started) * 1000),
            "output": output,
            "status": "completed",
            "completed_at": int(time.time()),
        }
        return result

    def submit_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return self._post("/api/v1/inference/report", result)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WattCoin Raspberry Pi inference relay scaffold")
    parser.add_argument("--once", action="store_true", help="Run one local mock relay job")
    parser.add_argument("--prompt", default="Hello from WattCoin relay", help="Prompt for local mock job")
    parser.add_argument("--submit", action="store_true", help="Submit mock result to API")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = RelayConfig.from_env()
    relay = InferenceRelay(cfg)

    if not args.once:
        print("Use --once for scaffold mode.")
        return 0

    result = relay.run_once({"prompt": args.prompt})
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.submit:
        ack = relay.submit_result(result)
        print(json.dumps({"submit_ack": ack}, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
