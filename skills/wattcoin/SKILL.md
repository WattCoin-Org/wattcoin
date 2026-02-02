# WattCoin Skill

Pay and earn WATT tokens for agent tasks on Solana.

## Overview

WattCoin (WATT) is a utility token for AI/agent automation. This skill enables agents to:
- Check WATT balances
- Send WATT payments
- Query LLMs via paid proxy (500 WATT/query)
- Scrape URLs via API
- Discover and complete agent tasks for rewards

## Setup

### 1. Environment Variables
```bash
export WATT_WALLET_PRIVATE_KEY="your_base58_private_key"
# OR
export WATT_WALLET_FILE="~/.wattcoin/wallet.json"
```

### 2. Requirements
- SOL: ~0.01 for transaction fees
- WATT: For payments (500 per LLM query, varies for tasks)

### 3. Install
```bash
pip install solana requests base58
```

## Functions

### `watt_balance(wallet=None)`
Check WATT balance for any wallet (defaults to your wallet).
```python
balance = watt_balance()  # Your balance
balance = watt_balance("7vvNkG3...")  # Other wallet
```

### `watt_send(to, amount)`
Send WATT to an address. Returns transaction signature.
```python
tx_sig = watt_send("7vvNkG3...", 1000)
```

### `watt_query(prompt)`
Query Grok via LLM proxy. Auto-sends 500 WATT, returns AI response.
```python
response = watt_query("What is Solana?")
print(response["response"])
```

### `watt_scrape(url, format="text")`
Scrape URL via WattCoin API. Free tier: 100 req/hr.
```python
content = watt_scrape("https://example.com")
```

### `watt_tasks()`
List available agent tasks with WATT rewards.
```python
tasks = watt_tasks()
for task in tasks["tasks"]:
    print(f"#{task['id']}: {task['title']} - {task['amount']} WATT")
```

### `watt_submit(task_id, result, wallet)`
Format task submission for GitHub issue comment.
```python
submission = watt_submit(20, {"mentions": [...]}, "7tYQQX8...")
# Returns formatted comment text to post
```

## Examples

```python
from wattcoin import *

# Check balance
print(f"Balance: {watt_balance()} WATT")

# Query LLM (costs 500 WATT)
answer = watt_query("Explain proof of stake in 2 sentences")
print(answer["response"])

# Find tasks
tasks = watt_tasks()
print(f"Found {tasks['count']} tasks worth {tasks['total_watt']} WATT")

# Scrape a page
content = watt_scrape("https://docs.solana.com")
```

## Constants

| Name | Value |
|------|-------|
| WATT_MINT | `Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump` |
| API_BASE | `https://wattcoin-production-81a7.up.railway.app` |
| BOUNTY_WALLET | `7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF` |

## Resources

- [WattCoin GitHub](https://github.com/WattCoin-Org/wattcoin)
- [CONTRIBUTING.md](https://github.com/WattCoin-Org/wattcoin/blob/main/CONTRIBUTING.md)
- [API Docs](https://wattcoin-production-81a7.up.railway.app/api/v1/bounties)
