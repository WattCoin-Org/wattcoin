#!/usr/bin/env python3
"""Parse and categorize WATT payment memos from Solana transactions.

Example:
  python tools/memo_parser.py --max-signatures 200 --output docs/samples/watt_memo_report.sample.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import requests
import time

DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
DEFAULT_WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
DEFAULT_MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"


def parse_date_to_epoch(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def classify_memo(memo: str) -> str:
    normalized = memo.strip().lower()
    if normalized.startswith("wattcoin bounty"):
        return "bounty_payment"
    if normalized.startswith("swarmsolve:payment:"):
        return "swarmsolve_payment"
    if normalized.startswith("swarmsolve:expired:"):
        return "swarmsolve_refund"
    if normalized.startswith("task:payout:"):
        return "task_payout"
    if normalized.startswith("wsi:payout:") or "wsi" in normalized and "payout" in normalized:
        return "wsi_payout"
    return "other"


def _extract_keys(message: Dict[str, Any]) -> List[str]:
    keys = message.get("accountKeys") or []
    result: List[str] = []
    for key in keys:
        if isinstance(key, str):
            result.append(key)
        elif isinstance(key, dict):
            pubkey = key.get("pubkey")
            if pubkey:
                result.append(pubkey)
    return result


def _memo_from_instruction(instruction: Dict[str, Any]) -> Optional[str]:
    parsed = instruction.get("parsed")
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict):
        if parsed.get("type") == "memo":
            value = parsed.get("info")
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                return value.get("memo")
        memo = parsed.get("memo")
        if isinstance(memo, str):
            return memo

    if instruction.get("programId") == DEFAULT_MEMO_PROGRAM:
        data = instruction.get("data")
        if isinstance(data, str):
            return data

    if instruction.get("program") in {"spl-memo", "memo"}:
        data = instruction.get("data")
        if isinstance(data, str):
            return data

    return None


def extract_memo_texts(tx: Dict[str, Any]) -> List[str]:
    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    meta = tx.get("meta") or {}

    instructions: List[Dict[str, Any]] = list(message.get("instructions") or [])
    for inner in meta.get("innerInstructions") or []:
        instructions.extend(inner.get("instructions") or [])

    memos: List[str] = []
    for instruction in instructions:
        memo = _memo_from_instruction(instruction)
        if memo:
            memos.append(memo)
    return memos


def extract_watt_amount(tx: Dict[str, Any], mint: str) -> float:
    """Estimate transferred WATT using token balance deltas.

    We sum all positive deltas for balances matching the target mint.
    """
    meta = tx.get("meta") or {}
    pre = meta.get("preTokenBalances") or []
    post = meta.get("postTokenBalances") or []

    decimals = None
    pre_map: Dict[int, int] = {}
    post_map: Dict[int, int] = {}

    for item in pre:
        if item.get("mint") != mint:
            continue
        idx = item.get("accountIndex")
        amount = int((item.get("uiTokenAmount") or {}).get("amount") or 0)
        pre_map[idx] = amount
        decimals = (item.get("uiTokenAmount") or {}).get("decimals", decimals)

    for item in post:
        if item.get("mint") != mint:
            continue
        idx = item.get("accountIndex")
        amount = int((item.get("uiTokenAmount") or {}).get("amount") or 0)
        post_map[idx] = amount
        decimals = (item.get("uiTokenAmount") or {}).get("decimals", decimals)

    if decimals is None:
        return 0.0

    total_raw_increase = 0
    for idx in set(pre_map) | set(post_map):
        before = pre_map.get(idx, 0)
        after = post_map.get(idx, 0)
        delta = after - before
        if delta > 0:
            total_raw_increase += delta

    scale = Decimal(10) ** Decimal(decimals)
    return float((Decimal(total_raw_increase) / scale).quantize(Decimal("0.000001")))


def tx_mentions_wallet(tx: Dict[str, Any], wallet: Optional[str]) -> bool:
    if not wallet:
        return True
    message = (tx.get("transaction") or {}).get("message") or {}
    return wallet in _extract_keys(message)


class SolanaRpcClient:
    def __init__(self, rpc_url: str, timeout: int = 30) -> None:
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.session = requests.Session()

    def call(self, method: str, params: List[Any]) -> Any:
        retries = 3
        delay_seconds = 1.0

        for attempt in range(1, retries + 1):
            response = self.session.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=self.timeout,
            )

            if response.status_code == 429 and attempt < retries:
                time.sleep(delay_seconds)
                delay_seconds *= 2
                continue

            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(f"RPC error for {method}: {payload['error']}")
            return payload.get("result")

        raise RuntimeError(f"RPC call failed for {method} after {retries} attempts")

    def get_signatures_for_address(self, address: str, limit: int, before: Optional[str] = None) -> List[Dict[str, Any]]:
        config: Dict[str, Any] = {"limit": limit}
        if before:
            config["before"] = before
        return self.call("getSignaturesForAddress", [address, config])

    def get_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        return self.call(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )


def iter_signatures(
    client: SolanaRpcClient,
    address: str,
    max_signatures: int,
) -> Iterable[Dict[str, Any]]:
    fetched = 0
    before: Optional[str] = None
    while fetched < max_signatures:
        remaining = max_signatures - fetched
        page = client.get_signatures_for_address(address, limit=min(1000, remaining), before=before)
        if not page:
            break

        for item in page:
            yield item
            fetched += 1
            if fetched >= max_signatures:
                break

        before = page[-1].get("signature")


def build_report(
    client: SolanaRpcClient,
    mint: str,
    max_signatures: int,
    start_epoch: Optional[int],
    end_epoch: Optional[int],
    wallet_filter: Optional[str],
) -> Dict[str, Any]:
    transactions: List[Dict[str, Any]] = []
    category_summary: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "total_watt": 0.0})

    scanned = 0
    for item in iter_signatures(client, mint, max_signatures=max_signatures):
        scanned += 1
        signature = item.get("signature")
        block_time = item.get("blockTime")

        if start_epoch and (block_time is None or block_time < start_epoch):
            continue
        if end_epoch and (block_time is None or block_time > end_epoch):
            continue

        tx = client.get_transaction(signature)
        if not tx:
            continue
        if not tx_mentions_wallet(tx, wallet_filter):
            continue

        memos = extract_memo_texts(tx)
        if not memos:
            continue

        amount = extract_watt_amount(tx, mint)
        memo = memos[0]
        category = classify_memo(memo)

        record = {
            "signature": signature,
            "slot": tx.get("slot"),
            "block_time": block_time,
            "memo": memo,
            "all_memos": memos,
            "category": category,
            "amount_watt": amount,
            "accounts": _extract_keys((tx.get("transaction") or {}).get("message") or {}),
        }
        transactions.append(record)

        category_summary[category]["count"] += 1
        category_summary[category]["total_watt"] = round(category_summary[category]["total_watt"] + amount, 6)

    total_watt = round(sum(entry["total_watt"] for entry in category_summary.values()), 6)
    category_breakdown = {key: value for key, value in sorted(category_summary.items())}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rpc_url": client.rpc_url,
        "mint": mint,
        "filters": {
            "start_date_epoch": start_epoch,
            "end_date_epoch": end_epoch,
            "wallet": wallet_filter,
            "max_signatures": max_signatures,
        },
        "scanned_signatures": scanned,
        "matched_transactions": len(transactions),
        "total_watt": total_watt,
        "category_breakdown": category_breakdown,
        "transactions": transactions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan WATT transactions and parse payment memos")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="Solana RPC URL")
    parser.add_argument("--mint", default=DEFAULT_WATT_MINT, help="WATT mint address")
    parser.add_argument("--wallet", help="Filter transactions involving a wallet")
    parser.add_argument("--start-date", help="ISO date/time, e.g. 2026-03-01 or 2026-03-01T00:00:00Z")
    parser.add_argument("--end-date", help="ISO date/time")
    parser.add_argument("--max-signatures", type=int, default=500, help="Max mint signatures to inspect")
    parser.add_argument("--output", default="watt_memo_report.json", help="Output JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_epoch = parse_date_to_epoch(args.start_date)
    end_epoch = parse_date_to_epoch(args.end_date)

    client = SolanaRpcClient(args.rpc_url)
    report = build_report(
        client=client,
        mint=args.mint,
        max_signatures=args.max_signatures,
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        wallet_filter=args.wallet,
    )

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    print(f"Report written to {args.output}")
    print(f"Matched transactions: {report['matched_transactions']}")
    print(f"Total WATT: {report['total_watt']}")


if __name__ == "__main__":
    main()
