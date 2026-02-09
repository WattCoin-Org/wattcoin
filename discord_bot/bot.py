import os
import discord
from discord import app_commands
from discord.ext import commands
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
import json
import base58
import logging
import re

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wattbot")

# Config with defaults
TOKEN = os.getenv("DISCORD_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")
WATT_MINT = os.getenv("WATT_MINT", "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump")
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://solana.publicnode.com")

# Retry configuration for network calls
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

def is_valid_solana_address(address: str) -> bool:
    """Validate Solana address using base58 decoding and regex."""
    if not address or not (32 <= len(address) <= 44):
        return False
    if not re.match(r"^[1-9A-HJ-NP-Za-km-z]+$", address):
        return False
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False

class WattBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        logger.info(f"Synced slash commands for {self.user}")

bot = WattBot()

@bot.event
async def on_ready():
    logger.info(f'⚡ WattCoin Bot logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="/bounties"))

@bot.tree.command(name="balance", description="Check WATT balance for any Solana wallet")
@app_commands.describe(wallet="The Solana wallet address to check")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def balance(interaction: discord.Interaction, wallet: str):
    # Input validation
    if not is_valid_solana_address(wallet):
        await interaction.response.send_message("❌ Invalid Solana wallet address.", ephemeral=True)
        return

    await interaction.response.defer()
    try:
        # Solana RPC call
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"mint": WATT_MINT},
                {"encoding": "jsonParsed"}
            ]
        }
        resp = http.post(SOLANA_RPC, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        accounts = data.get("result", {}).get("value", [])
        if not accounts:
            await interaction.followup.send(f"ℹ️ No WATT account found for `{wallet[:8]}...`. The wallet may not hold any WATT tokens.")
            return
            
        token_data = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        balance_amount = token_data["uiAmount"]
        
        embed = discord.Embed(
            title="💰 WATT Balance",
            description=f"Wallet: `{wallet}`",
            color=0x00FF00,
            timestamp=datetime.now()
        )
        embed.add_field(name="Amount", value=f"**{balance_amount:,.2f} WATT**", inline=False)
        embed.set_footer(text="WattCoin Network")
        
        await interaction.followup.send(embed=embed)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"RPC error: {e}")
        await interaction.followup.send("❌ Error connecting to Solana network. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await interaction.followup.send("❌ An unexpected error occurred.")

@bot.tree.command(name="bounties", description="List open bounties and agent tasks")
@app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
async def bounties(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        resp = http.get(f"{API_BASE_URL}/api/v1/bounties?status=open", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])[:10] # Top 10
        
        embed = discord.Embed(
            title="⚡ Open Bounties",
            description=f"Total: {data.get('total_bounties', 0)} | Agent Tasks: {data.get('total_agent_tasks', 0)}",
            color=0x4f46e5,
            url="https://github.com/WattCoin-Org/wattcoin/issues?q=is%3Aopen+label%3Abounty",
            timestamp=datetime.now()
        )
        
        if not items:
            embed.description = "No open bounties at the moment. Check back later!"
        else:
            for b in items:
                tier_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(b.get('tier'), "⚪")
                embed.add_field(
                    name=f"{tier_emoji} {b.get('title')}",
                    value=f"Reward: **{b.get('amount', 0):,} WATT** | [View Issue]({b.get('url')})",
                    inline=False
                )
        
        embed.set_footer(text="Join the network: https://github.com/WattCoin-Org/wattcoin")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Bounty API error: {e}")
        await interaction.followup.send("❌ Could not fetch bounties. The API might be offline.")

@bot.tree.command(name="stats", description="Get network-wide statistics")
@app_commands.checks.cooldown(1, 15.0, key=lambda i: (i.guild_id, i.user.id))
async def stats(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        resp = http.get(f"{API_BASE_URL}/api/v1/stats", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        embed = discord.Embed(
            title="📊 WattCoin Network Stats",
            color=0x3498DB,
            timestamp=datetime.now()
        )
        
        nodes = data.get("nodes", {})
        embed.add_field(name="Nodes", value=f"🟢 {nodes.get('active', 0)} Active\n⚪ {nodes.get('total_registered', 0)} Total", inline=True)
        
        reliability = data.get("reliability", {})
        embed.add_field(name="Reliability", value=f"Avg Score: {reliability.get('avg_score', 0)}/100", inline=True)
        
        payouts = data.get("payouts", {})
        embed.add_field(name="WATT Distributed", value=f"**{payouts.get('total_watt', 0):,} WATT**", inline=False)
        
        jobs = data.get("jobs", {})
        embed.add_field(name="Jobs Completed", value=f"{jobs.get('total_completed', 0):,}", inline=True)
        
        embed.set_footer(text="WattCoin Infrastructure")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Stats API error: {e}")
        await interaction.followup.send("❌ Error fetching network statistics.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s.", ephemeral=True)
    else:
        logger.error(f"Slash command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An error occurred processing the command.", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_TOKEN environment variable is missing")
    else:
        bot.run(TOKEN)
