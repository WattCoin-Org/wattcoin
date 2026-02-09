import os
import discord
from discord.ext import commands
from discord import app_commands
import requests
import logging
from datetime import datetime
import base58

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WattCoinBot")

# Environment Variables
TOKEN = os.getenv("DISCORD_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.wattcoin.org")
WATT_MINT = os.getenv("WATT_MINT")
SOLANA_RPC = os.getenv("SOLANA_RPC")

class WattBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        logger.info(f"Synced slash commands for {self.user}")

bot = WattBot()
http = requests.Session()

def validate_solana_address(address: str) -> bool:
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except:
        return False

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="/balance | /stats"))

@bot.tree.command(name="balance", description="Check WATT balance and node status for a Solana wallet")
@app_commands.describe(address="Your Solana wallet address")
async def balance(interaction: discord.Interaction, address: str):
    if not validate_solana_address(address):
        await interaction.response.send_message("❌ Invalid Solana address format.", ephemeral=True)
        return

    await interaction.response.defer()
    try:
        # Fetch account info from Solana RPC (simplified example)
        # In production, use solana-py or specific API endpoints
        resp = http.get(f"{API_BASE_URL}/api/v1/nodes/account/{address}", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        embed = discord.Embed(
            title="💰 Wallet Overview",
            description=f"Address: `{address[:6]}...{address[-6:]}`",
            color=0x00FFA3,
            timestamp=datetime.now()
        )
        
        balance_val = data.get("balance", 0)
        nodes_active = data.get("active_nodes", 0)
        total_earned = data.get("total_earned", 0)

        embed.add_field(name="Current Balance", value=f"**{balance_val:,.2f} WATT**", inline=True)
        embed.add_field(name="Active Nodes", value=f"**{nodes_active}**", inline=True)
        embed.add_field(name="Total Life-time Earned", value=f"**{total_earned:,.2f} WATT**", inline=False)
        
        embed.set_footer(text="Data provided by WattCoin Network")
        await interaction.followup.send(embed=embed)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            await interaction.followup.send("🔍 Wallet not found in WattCoin database. Are you running a node?")
        else:
            await interaction.followup.send("⚠️ Error fetching data from network.")
    except Exception as e:
        logger.error(f"Balance command error: {e}")
        await interaction.followup.send("❌ An unexpected error occurred.")

@bot.tree.command(name="bounties", description="List active open-source bounties")
async def bounties(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        resp = http.get(f"{API_BASE_URL}/api/v1/bounties/active", timeout=10)
        resp.raise_for_status()
        items = resp.json()

        embed = discord.Embed(
            title="🚀 Active Bounties",
            description="Contribute and earn WATT",
            color=0xF1C40F
        )

        if not items:
            embed.description = "No active bounties at the moment. Check back later!"
        else:
            for b in items[:10]: # Limit to top 10 to avoid embed size issues
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
async def stats(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        resp = http.get(f"{API_BASE_URL}/api/v1/stats", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        embed = discord.Embed(
            title="📊 WattCoin Network Stats",
            description="Real-time infrastructure metrics",
            color=0x3498DB,
            timestamp=datetime.now()
        )
        
        nodes = data.get("nodes", {})
        network = data.get("network", {})

        embed.add_field(name="Total Nodes", value=f"**{nodes.get('total', 0):,}**", inline=True)
        embed.add_field(name="Online Capacity", value=f"**{nodes.get('online_percent', 0)}%**", inline=True)
        embed.add_field(name="Network Hashrate", value=f"**{network.get('hashrate', '0 H/s')}**", inline=False)
        embed.add_field(name="Total Distributed", value=f"**{network.get('total_distributed', 0):,.0f} WATT**", inline=False)
        
        embed.set_footer(text="WattCoin v1.2.0-mainnet")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Stats command error: {e}")
        await interaction.followup.send("❌ Error fetching network statistics.")

if __name__ == "__main__":
    if not TOKEN:
        logger.critical("DISCORD_TOKEN environment variable is missing.")
        exit(1)
        
    if not WATT_MINT:
        logger.critical("WATT_MINT environment variable is missing.")
        exit(1)
        
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.critical("Failed to log in: Invalid DISCORD_TOKEN provided.")
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}")
    finally:
        http.close()

