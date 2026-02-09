# WattCoin Discord Bot

A Discord bot for the WattCoin community to check balances, view open bounties, and monitor network statistics.

## Commands

- `/balance <wallet>`: Check the WATT balance of any Solana wallet.
- `/bounties`: List the latest open bounties and agent tasks from GitHub.
- `/stats`: View network-wide statistics (active nodes, total payouts, etc.).

## Setup

### 1. Requirements
- Python 3.10+
- A Discord Bot Token (from [Discord Developer Portal](https://discord.com/developers/applications))

### 2. Environment Variables
Create a `.env` file or set the following environment variables:
- `DISCORD_TOKEN`: Your bot token.
- `API_BASE_URL`: The base URL of the WattCoin API (default: `http://localhost:5000`).

### 3. Installation

#### Using Docker (Recommended)
```bash
docker build -t wattcoin-bot .
docker run -e DISCORD_TOKEN=your_token_here wattcoin-bot
```

#### Manual Installation
```bash
pip install -r requirements.txt
python bot.py
```

## How to Claim Bounties
Bounty data is fetched directly from the WattCoin GitHub API. To claim a bounty:
1. View the issue using the link provided by the bot.
2. Follow the instructions in `CONTRIBUTING.md`.
3. Submit your PR.
