# WattCoin Discord Bot

A Discord bot for the WattCoin community server to monitor balances, stats, and network activity.

## Features

- **Slash Commands**:
  - `/balance <wallet>` — Check WATT balance for any Solana wallet.
  - `/bounties` — List current open bounties.
  - `/stats` — View live network stats (active nodes, payouts).
  - `/price` — Current WATT price from DexScreener.
  - `/leaderboard` — Top 5 contributors.
- **Alerts**:
  - Background task polls for new bounties and PR payments every 5 minutes.
  - Posts updates to the `#alerts` channel.

## Setup

### 1. Create a Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a "New Application".
3. Under **Bot**, enable "Message Content Intent".
4. Copy the **Token**.

### 2. Environment Variables
Create a `.env` file or set the following:
- `DISCORD_TOKEN`: Your bot token.
- `DISCORD_GUILD_ID`: (Optional) ID of your server for instant command sync.

### 3. Run with Docker
```bash
docker build -t wattcoin-bot .
docker run -e DISCORD_TOKEN=your_token_here wattcoin-bot
```

### 4. Run with Python
```bash
pip install -r requirements.txt
python bot.py
```

## Invite Link Generation
To invite the bot, use the following URL (replace `YOUR_CLIENT_ID`):
`https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147483648&scope=bot%20applications.commands`
