# WattCoin Transaction Memo Parser

Python script that scans Solana blockchain for WATT token transactions and extracts/categorizes payment memos.

## Task Reference

- **Issue**: [#240](https://github.com/WattCoin-Org/wattcoin/issues/240)
- **Reward**: 8,000 WATT
- **Author**: hello46871574

## Features

- 🔍 Scan WATT token transactions on Solana mainnet
- 📝 Extract and parse memo program data
- 🏷️ Auto-categorize transactions:
  - `bounty_payment` - WattCoin bounty rewards
  - `swarmsolve_payment` - SwarmSolve solution payments
  - `swarmsolve_refund` - Expired SwarmSolve refunds
  - `task_payout` - Task completion payouts
  - `wsi_payout` - WSI query payouts
  - `other` - Other WATT transfers
  - `unknown` - Unrecognized memo format
- 📊 Generate JSON report with summary statistics
- 🎯 Filter by date range and wallet address

## Installation

```bash
# Install dependencies
pip3 install solders base58 requests

# Or use requirements.txt
pip3 install -r requirements.txt
```

## Usage

### Basic Usage (scan last 1000 transactions)

```bash
python3 memo_parser.py
```

### Scan with date range

```bash
python3 memo_parser.py --start-date 2026-03-01 --end-date 2026-03-10
```

### Filter by specific wallet

```bash
python3 memo_parser.py --wallet 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF
```

### Custom output file

```bash
python3 memo_parser.py --output my_report.json
```

### Use custom RPC endpoint

```bash
python3 memo_parser.py --rpc-url https://api.mainnet-beta.solana.com
```

### Quiet mode (no progress output)

```bash
python3 memo_parser.py --quiet
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--start-date` | Start date (YYYY-MM-DD) | None (no limit) |
| `--end-date` | End date (YYYY-MM-DD) | None (no limit) |
| `--wallet` | Filter by wallet address | None |
| `--max-txns` | Maximum transactions to scan | 1000 |
| `--output` | Output JSON file path | memo_report.json |
| `--rpc-url` | Solana RPC endpoint | https://solana.publicnode.com |
| `--quiet` | Suppress progress output | False |

## Output Format

The generated JSON report contains:

```json
{
  "generated_at": "2026-03-10T00:00:00",
  "summary": {
    "total_transactions": 100,
    "total_watt": 50000.0,
    "by_category": {
      "bounty_payment": {
        "count": 20,
        "total_watt": 30000.0,
        "transactions": [...]
      },
      "task_payout": {
        "count": 50,
        "total_watt": 15000.0,
        "transactions": [...]
      }
    },
    "date_range": {
      "start": "2026-03-01T00:00:00",
      "end": "2026-03-10T23:59:59"
    }
  },
  "parser_stats": {
    "parsed_count": 70,
    "unknown_count": 30,
    "parse_rate": "70.0%"
  },
  "transactions": [
    {
      "tx_signature": "...",
      "timestamp": "2026-03-10T12:00:00",
      "category": "bounty_payment",
      "raw_memo": "WattCoin Bounty | PR #123 | Issue #456 | Score: 8.5 | 1000 WATT",
      "amount_watt": 1000.0,
      "issue_number": "456",
      "pr_number": "123",
      "score": 8.5
    }
  ]
}
```

## Memo Formats

The parser recognizes the following memo formats:

### Bounty Payment
```
WattCoin Bounty | PR #XX | Issue #YY | Score: Z/10 | AMOUNT WATT
```

### SwarmSolve Payment
```
swarmsolve:payment:SOLUTION_ID
```

### SwarmSolve Refund
```
swarmsolve:expired:SOLUTION_ID
```

### Task Payout
```
task:payout:TASK_ID
```

### WSI Payout
```
wsi:payout:TASK_ID
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SOLANA_RPC_URL` | Solana RPC endpoint | https://solana.publicnode.com |
| `WATT_WALLET_PRIVATE_KEY` | (Optional) For future write operations | None |

## Examples

### Example 1: Scan last 500 transactions and save report

```bash
python3 memo_parser.py --max-txns 500 --output march_report.json
```

### Example 2: Analyze bounty payments in March

```bash
python3 memo_parser.py \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --output bounty_march.json
```

### Example 3: Check specific wallet's transactions

```bash
python3 memo_parser.py \
  --wallet 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF \
  --max-txns 100
```

## Programmatic Usage

```python
from memo_parser import WattCoinMemoScanner, MemoParser

# Create scanner
scanner = WattCoinMemoScanner()

# Scan transactions
memos = scanner.scan(
    max_transactions=500,
    start_date=datetime(2026, 3, 1),
    end_date=datetime(2026, 3, 10)
)

# Generate report
report = scanner.generate_report(memos, output_file="report.json")

# Access parsed data
for memo in memos:
    print(f"{memo.category}: {memo.amount_watt} WATT")
```

## Performance Notes

- Scanning 1000 transactions typically takes 2-5 minutes
- Public RPC endpoints may have rate limits
- For heavy usage, consider using a dedicated RPC provider (QuickNode, Alchemy, etc.)

## Troubleshooting

### "RPC request failed" error
- Try a different RPC endpoint with `--rpc-url`
- Reduce `--max-txns` to scan fewer transactions
- Add delays between requests if hitting rate limits

### No transactions found
- Verify the WATT mint address is correct
- Check if the wallet has any WATT transactions
- Expand the date range

### Parse rate is low
- Some WATT transfers may not include memos
- New memo formats may need to be added to the parser

## License

MIT License - See LICENSE file in the main repository.

## Contributing

Found a bug or want to add support for new memo formats? Open an issue or PR!

---

**Task Submission**: This script was created for WattCoin Task #240.
**Submit via**: `POST /api/v1/tasks/task_11fa544b80b7/submit`
