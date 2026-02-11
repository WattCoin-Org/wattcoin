```python
import discord
from discord.ext import commands, tasks
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
BALANCE_API_URL = os.getenv('BALANCE_API_URL')
NETWORK_STATS_API_URL = os.getenv('NETWORK_STATS_API_URL')

# Initialize bot
bot = commands.Bot(command_prefix='!')

# Scheduler for alerts
scheduler = AsyncIOScheduler()

# In-memory storage for user alert configurations
user_alerts = {}

def fetch_balance(user_id):
    """Fetch user balance from external API."""
    try:
        response = requests.get(f"{BALANCE_API_URL}/{user_id}")
        response.raise_for_status()
        return response.json().get('balance', 'Balance not found')
    except requests.RequestException as e:
        return f"Error fetching balance: {str(e)}"

def fetch_network_stats():
    """Fetch network stats from external API."""
    try:
        response = requests.get(NETWORK_STATS_API_URL)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return f"Error fetching network stats: {str(e)}"

@bot.command(name='balance')
async def balance(ctx):
    """Command to check user balance."""
    user_id = ctx.author.id
    balance = fetch_balance(user_id)
    await ctx.send(f"Your balance is: {balance}")

@bot.command(name='set_alert')
async def set_alert(ctx, threshold: float):
    """Command to set balance alert threshold."""
    user_id = ctx.author.id
    user_alerts[user_id] = threshold
    await ctx.send(f"Alert set for balance below: {threshold}")

@tasks.loop(minutes=5)
async def check_alerts():
    """Check if any user balance falls below their alert threshold."""
    for user_id, threshold in user_alerts.items():
        balance = fetch_balance(user_id)
        if isinstance(balance, float) and balance < threshold:
            user = await bot.fetch_user(user_id)
            await user.send(f"Alert! Your balance is below {threshold}: {balance}")

@bot.command(name='network_stats')
async def network_stats(ctx):
    """Command to display network stats."""
    stats = fetch_network_stats()
    if isinstance(stats, dict):
        await ctx.send(f"Network Stats: {stats}")
    else:
        await ctx.send(stats)

@bot.event
async def on_ready():
    """Event handler for when the bot is ready."""
    print(f'Logged in as {bot.user.name}')
    check_alerts.start()

# Start the bot
scheduler.start()
bot.run(TOKEN)
```

This code sets up a Discord bot with balance inquiry, alert system, and network stats retrieval features. It uses `discord.py` for bot interactions, `requests` for API calls, and `APScheduler` for scheduling tasks. The bot securely loads configuration from a `.env` file.