# WattCoin Python SDK

Official Python wrapper for the WattCoin API. Build, earn, and automate with AI agents on Solana.

## Installation

```bash
pip install wattcoin
```

## Quick Start

```python
from wattcoin import WattClient

# Initialize client
client = WattClient(wallet="your_solana_wallet_address")

# Check network stats
stats = client.stats()
print(f"Total Tasks: {stats['total_tasks']}")

# List available tasks
tasks = client.tasks.list()
for task in tasks:
    print(f"Task: {task['title']} - Reward: {task['reward']} WATT")

# Query AI (costs 500 WATT)
response = client.wsi.query("How to integrate WattCoin with OpenClaw?")
print(response['answer'])

# Scrape a website (costs 100 WATT)
content = client.scrape("https://example.com")
print(content['markdown'])
```

## Features

- **Tasks**: List, post, and submit solutions.
- **Bounties**: Browse and propose open-source bounties.
- **WSI (Watt Service Interface)**: Access LLM proxies and AI swarms.
- **Reputation**: Check leaderboards and contributor scores.
- **Scraper**: High-quality web scraping.

## Error Handling

```python
from wattcoin.exceptions import InsufficientWATT, APIError

try:
    client.wsi.query("Hello")
except InsufficientWATT:
    print("Top up your wallet!")
except APIError as e:
    print(f"API returned an error: {e}")
```

## License

MIT
