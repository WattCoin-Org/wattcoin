#!/usr/bin/env python3
"""
Fetch top 50 Solana AI/agent-related tokens from DexScreener.

Outputs:
- JSON dataset with required token fields
- Markdown summary table sorted by market cap descending
"""

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


SEARCH_TERMS = [
    "ai",
    "agent",
    "automation",
    "llm",
    "inference",
    "compute",
    "bot",
    "gpt",
    "neural",
    "robot",
    "ml",
]

KEYWORDS = [
    "ai",
    "agent",
    "automation",
    "llm",
    "inference",
    "compute",
    "bot",
    "gpt",
    "neural",
    "robot",
    "ml",
]
KEYWORD_PATTERN = re.compile(
    r"(^|[^a-z0-9])(ai|agent|automation|llm|inference|compute|bot|gpt|neural|robot|ml)([^a-z0-9]|$)"
)


def http_get_json(url: str, retries: int = 5) -> dict:
    last_err = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "wattcoin-research-bot/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.0)
    raise RuntimeError(f"Failed request: {url}; last_error={last_err}")


def _to_float(value) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def is_ai_agent_pair(pair: dict) -> bool:
    base_name = ((pair.get("baseToken") or {}).get("name") or "").lower()
    base_symbol = ((pair.get("baseToken") or {}).get("symbol") or "").lower()
    hay = f"{base_name} {base_symbol}"
    return bool(KEYWORD_PATTERN.search(hay))


def normalize_pair(pair: dict) -> dict:
    base = pair.get("baseToken") or {}
    volume = pair.get("volume") or {}
    liquidity = pair.get("liquidity") or {}
    price = pair.get("priceUsd")
    market_cap = pair.get("marketCap")
    if market_cap is None:
        market_cap = pair.get("fdv")

    return {
        "name": base.get("name") or "Unknown",
        "ticker": base.get("symbol") or "UNKNOWN",
        "contract_address": base.get("address") or "",
        "market_cap_usd": _to_float(market_cap),
        "volume_24h_usd": _to_float(volume.get("h24")),
        "price_usd": _to_float(price),
        "liquidity_usd": _to_float(liquidity.get("usd")),
        "pair_address": pair.get("pairAddress") or "",
        "dex_id": pair.get("dexId") or "",
        "pair_url": pair.get("url") or "",
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def fetch_candidates() -> list[dict]:
    pairs = []
    for term in SEARCH_TERMS:
        q = urllib.parse.quote(term)
        url = f"https://api.dexscreener.com/latest/dex/search/?q={q}"
        payload = http_get_json(url)
        for pair in payload.get("pairs") or []:
            if (pair.get("chainId") or "").lower() != "solana":
                continue
            if not is_ai_agent_pair(pair):
                continue
            pairs.append(pair)
    return pairs


def build_top_tokens(limit: int = 50) -> list[dict]:
    pairs = fetch_candidates()
    by_contract = {}
    for pair in pairs:
        token = normalize_pair(pair)
        addr = token["contract_address"]
        if not addr:
            continue
        old = by_contract.get(addr)
        if old is None or token["market_cap_usd"] > old["market_cap_usd"]:
            by_contract[addr] = token

    tokens = list(by_contract.values())
    tokens.sort(key=lambda x: x["market_cap_usd"], reverse=True)
    return tokens[:limit]


def fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def write_outputs(tokens: list[dict], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "DexScreener API (latest/dex/search)",
        "filter": {
            "chain": "solana",
            "keywords": KEYWORDS,
            "search_terms": SEARCH_TERMS,
        },
        "count": len(tokens),
        "tokens": tokens,
    }
    json_path.write_text(json.dumps(payload, indent=2))

    lines = []
    lines.append("# Top 50 Solana AI/Agent Tokens (DexScreener) — Issue #142")
    lines.append("")
    lines.append("Sorted by market cap descending.")
    lines.append("")
    lines.append("| Rank | Name | Ticker | Contract | Market Cap | 24h Volume | Price | Liquidity | Pair |")
    lines.append("|---:|---|---|---|---:|---:|---:|---:|---|")
    for i, t in enumerate(tokens, 1):
        contract = f"`{t['contract_address']}`"
        pair = f"[{t['pair_address']}]({t['pair_url']})" if t["pair_url"] else f"`{t['pair_address']}`"
        lines.append(
            f"| {i} | {t['name']} | {t['ticker']} | {contract} | {fmt_money(t['market_cap_usd'])} | "
            f"{fmt_money(t['volume_24h_usd'])} | {fmt_money(t['price_usd'])} | {fmt_money(t['liquidity_usd'])} | {pair} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**Payout Wallet**: same wallet as prior approved payouts for `@hriszc` (can be posted explicitly in follow-up comment if required by maintainer checks).")
    md_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json-out",
        default="research/dexscreener-ai-agent-tokens.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--md-out",
        default="research/dexscreener-ai-agent-tokens.md",
        help="Output markdown file path",
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    tokens = build_top_tokens(limit=args.limit)
    write_outputs(tokens, Path(args.json_out), Path(args.md_out))
    print(f"Wrote {args.json_out} and {args.md_out} with {len(tokens)} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
