# WATT Memo Parser

`tools/memo_parser.py` scans Solana transactions for the WATT mint, extracts memo data, classifies payment types, and produces a JSON report.

## Features

- Configurable Solana RPC endpoint (`--rpc-url`)
- Scans signatures for the WATT mint address
- Extracts memo data from top-level + inner instructions
- Categorizes memo formats into:
  - `bounty_payment`
  - `swarmsolve_payment`
  - `swarmsolve_refund`
  - `task_payout`
  - `wsi_payout`
  - `other`
- Outputs:
  - detailed transaction list
  - category breakdown counts + total WATT
  - overall total WATT
- Optional filters:
  - date range (`--start-date`, `--end-date`)
  - wallet (`--wallet`)

## Usage

```bash
python tools/memo_parser.py \
  --rpc-url https://api.mainnet-beta.solana.com \
  --mint Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump \
  --max-signatures 250 \
  --start-date 2026-03-01T00:00:00Z \
  --end-date 2026-03-04T00:00:00Z \
  --output docs/samples/watt_memo_report.sample.json
```

## Output Schema (high-level)

```json
{
  "generated_at": "...",
  "rpc_url": "...",
  "mint": "...",
  "filters": {"...": "..."},
  "scanned_signatures": 250,
  "matched_transactions": 42,
  "total_watt": 13850.0,
  "category_breakdown": {
    "bounty_payment": {"count": 11, "total_watt": 9200.0},
    "task_payout": {"count": 8, "total_watt": 2200.0}
  },
  "transactions": [{"signature": "...", "memo": "...", "category": "...", "amount_watt": 250.0}]
}
```

## Tests

```bash
python -m unittest tools/tests/test_memo_parser.py
```
