# WattCoin Discord Bot

A Discord bot for the WattCoin ecosystem, providing balance checks, bounty alerts, and price tracking.

## Features

- **/balance [address]**: Check WATT balance of a Solana address.
- **/price**: Get current WATT price from DexScreener.
- **/bounties**: List active bounties.
- **/tasks**: List available tasks.
- **/stats**: View WattCoin ecosystem statistics.
- **/leaderboard**: View top contributors.
- **Automated Alerts**: Real-time notifications for new bounties, merged PRs, and tier promotions.

## Setup

1. Clone the repository.
2. Navigate to `tools/discord-bot/`.
3. Create a `.env` file based on `.env.example`.
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the bot:
   ```bash
   python main.py
   ```

## Docker

Build and run using Docker:
```bash
docker build -t wattcoin-bot .
docker run --env-file .env wattcoin-bot
```

## Environment Variables

- `DISCORD_BOT_TOKEN`: Your Discord bot token.
- `DISCORD_ALERTS_CHANNEL`: Channel ID where alerts will be sent.
- `WATTCOIN_API_URL`: Base URL for the WattCoin API.
- `SOLANA_RPC_URL`: Solana RPC endpoint.
