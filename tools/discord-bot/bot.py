import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import requests
import aiohttp
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = os.getenv('DISCORD_GUILD_ID')
API_BASE = "https://wattcoin-production-81a7.up.railway.app"
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"

class WattBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync slash commands
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        
        # Start background tasks
        self.alert_check.start()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    @tasks.loop(minutes=5)
    async def alert_check(self):
        """Check for new bounties, PR merges, and solutions to post to alerts channel"""
        alerts_channel_name = "alerts"
        channel = discord.utils.get(self.get_all_channels(), name=alerts_channel_name)
        if not channel:
            return

        try:
            # 1. Check for new bounties
            url = f"{API_BASE}/api/v1/bounties"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bounties_list = data.get('bounties', [])
                        # Logic to track seen bounties would go here (e.g., local json file)
                        # For now, just logging the check
                        print(f"Bounty check: {len(bounties_list)} open")

            # 2. Check for merged PRs / Payouts
            stats_url = f"{API_BASE}/api/v1/bounty-stats"
            async with aiohttp.ClientSession() as session:
                async with session.get(stats_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        recent_payouts = data.get('recent_payouts', [])
                        # Logic to track seen payouts would go here
                        print(f"Payout check: {len(recent_payouts)} recent")

        except Exception as e:
            print(f"Alert check error: {e}")

    @alert_check.before_loop
    async def before_alert_check(self):
        await self.wait_until_ready()

bot = WattBot()

@bot.tree.command(name="balance", description="Check WATT balance for a Solana wallet")
@app_commands.describe(wallet="Solana wallet address")
async def balance(interaction: discord.Interaction, wallet: str):
    await interaction.response.defer()
    try:
        # Use Solana RPC or WattCoin API to get balance
        # For now, using a placeholder logic that calls the API if available
        url = f"{API_BASE}/api/v1/balance/{wallet}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_amount = data.get('balance', 0)
                    await interaction.followup.send(f"💰 **Wallet Balance**\nAddress: `{wallet}`\nBalance: `{balance_amount:,.2f} WATT`")
                else:
                    await interaction.followup.send(f"❌ Error fetching balance: {resp.status}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.command(name="bounties", description="List open bounties with reward amounts")
async def bounties(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        url = f"{API_BASE}/api/v1/bounties"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    bounties_list = data.get('bounties', [])
                    if not bounties_list:
                        return await interaction.followup.send("No open bounties found.")
                    
                    embed = discord.Embed(title="🚀 Open Bounties", color=0x39ff14)
                    for b in bounties_list[:10]:  # Limit to 10 for embed
                        embed.add_field(
                            name=f"#{b['id']} - {b['title']}", 
                            value=f"Reward: `{b['reward']:,} WATT` | [Link]({b.get('url', '#')})", 
                            inline=False
                        )
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ Error fetching bounties: {resp.status}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.command(name="stats", description="Live network stats")
async def stats(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        url = f"{API_BASE}/api/v1/stats"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    nodes = data.get('active_nodes', 0)
                    payouts = data.get('total_payouts', 0)
                    tasks_count = data.get('open_tasks', 0)
                    
                    embed = discord.Embed(title="📊 WattCoin Network Stats", color=0x39ff14)
                    embed.add_field(name="Active Nodes", value=f"`{nodes}`", inline=True)
                    embed.add_field(name="Total Payouts", value=f"`{payouts:,.0f} WATT`", inline=True)
                    embed.add_field(name="Open Tasks", value=f"`{tasks_count}`", inline=True)
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ Error fetching stats: {resp.status}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.command(name="price", description="Current WATT price from DexScreener")
async def price(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{WATT_MINT}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pair = data.get('pair', {})
                    price_usd = pair.get('priceUsd', '0.00')
                    mcap = pair.get('fdv', 0)
                    
                    embed = discord.Embed(title="📈 WATT Price (DexScreener)", color=0x39ff14)
                    embed.add_field(name="Price USD", value=f"`${price_usd}`", inline=True)
                    embed.add_field(name="Market Cap (FDV)", value=f"`${mcap:,.0f}`", inline=True)
                    embed.set_footer(text="Data from DexScreener")
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ Error fetching price: {resp.status}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.command(name="leaderboard", description="Top 5 contributors by tier and earnings")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        url = f"{API_BASE}/api/v1/leaderboard"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    top_5 = data.get('top_contributors', [])
                    
                    embed = discord.Embed(title="🏆 Contributor Leaderboard", color=0x39ff14)
                    for i, c in enumerate(top_5, 1):
                        embed.add_field(
                            name=f"{i}. {c['github']} ({c['tier'].capitalize()})",
                            value=f"Earned: `{c['total_earned']:,} WATT`",
                            inline=False
                        )
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ Error fetching leaderboard: {resp.status}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in environment variables.")
    else:
        bot.run(TOKEN)
