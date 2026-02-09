import os
import discord
from discord import app_commands
from discord.ext import commands
import requests
from datetime import datetime
import json

# Config
TOKEN = os.getenv("DISCORD_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
SOLANA_RPC = "https://solana.publicnode.com"

class WattBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = WattBot()

@bot.event
async def on_ready():
    print(f'⚡ WattCoin Bot logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="/bounties"))

@bot.tree.command(name="balance", description="Check WATT balance for any Solana wallet")
@app_commands.describe(wallet="The Solana wallet address to check")
async def balance(interaction: discord.Interaction, wallet: str):
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
        resp = requests.post(SOLANA_RPC, json=payload, timeout=15)
        data = resp.json()
        
        accounts = data.get("result", {}).get("value", [])
        if not accounts:
            await interaction.followup.send(f"❌ No WATT account found for `{wallet[:8]}...` (or wallet is invalid)")
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
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error checking balance: {str(e)}")

@bot.tree.command(name="bounties", description="List open bounties and agent tasks")
async def bounties(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        resp = requests.get(f"{API_BASE_URL}/api/v1/bounties?status=open", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])[:10] # Top 10
            
            embed = discord.Embed(
                title="⚡ Open Bounties",
                description=f"Total: {data.get('total_bounties')} | Agent Tasks: {data.get('total_agent_tasks')}",
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
                        value=f"Reward: **{b.get('amount'):,} WATT** | [View Issue]({b.get('url')})",
                        inline=False
                    )
            
            embed.set_footer(text="Join the network: /register")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Could not fetch bounties from API. Is the server running?")
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching bounties: {str(e)}")

@bot.tree.command(name="stats", description="Get network-wide statistics")
async def stats(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        resp = requests.get(f"{API_BASE_URL}/api/v1/stats", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            
            embed = discord.Embed(
                title="📊 WattCoin Network Stats",
                color=0x3498DB,
                timestamp=datetime.now()
            )
            
            nodes = data.get("nodes", {})
            embed.add_field(name="Nodes", value=f"🟢 {nodes.get('active')} Active\n⚪ {nodes.get('total_registered')} Total", inline=True)
            
            reliability = data.get("reliability", {})
            embed.add_field(name="Reliability", value=f"Avg Score: {reliability.get('avg_score')}/100", inline=True)
            
            payouts = data.get("payouts", {})
            embed.add_field(name="WATT Distributed", value=f"**{payouts.get('total_watt'):,} WATT**", inline=False)
            
            jobs = data.get("jobs", {})
            embed.add_field(name="Jobs Completed", value=f"{jobs.get('total_completed'):,}", inline=True)
            
            embed.set_footer(text="WattCoin Infrastructure")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Could not fetch stats from API.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching stats: {str(e)}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not set")
    else:
        bot.run(TOKEN)
