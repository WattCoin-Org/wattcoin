"""WattCoin Discord Bot - Bounty #150 (10,000 WATT)
Commands: /balance, /stats, /alerts
"""
import os
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks, commands
from solders.pubkey import Pubkey
from solders.rpc.api import Client as SolanaClient
from datetime import datetime

# Config
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
WATTCOIN_API = "https://wattcoin.org/api/v1"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Bot state
alert_channels = set()  # Channels subscribed to alerts
network_cache = {}


class WattCoinBot:
    def __init__(self):
        self.solana = SolanaClient(SOLANA_RPC)
    
    async def get_watt_balance(self, wallet_address: str) -> dict:
        """Get WATT token balance for a wallet."""
        try:
            # Validate address
            pubkey = Pubkey.from_string(wallet_address)
            
            # Get token accounts
            mint_pubkey = Pubkey.from_string(WATT_MINT)
            
            # Fetch balance (simplified - actual implementation needs token account lookup)
            response = await self._rpc_call("getTokenAccountsByOwner", [
                str(pubkey),
                {"mint": str(mint_pubkey)},
                {"encoding": "jsonParsed"}
            ])
            
            if response and 'result' in response and response['result']['value']:
                account = response['result']['value'][0]
                balance = account['account']['data']['parsed']['info']['tokenAmount']['uiAmount']
                return {"success": True, "balance": balance, "wallet": wallet_address}
            else:
                return {"success": True, "balance": 0, "wallet": wallet_address}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_network_stats(self) -> dict:
        """Get WattCoin network statistics."""
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch from WattCoin API
                async with session.get(f"{WATTCOIN_API}/stats") as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {
                            "active_nodes": "N/A",
                            "total_tasks": "N/A",
                            "pending_bounties": "N/A",
                            "error": f"API returned {resp.status}"
                        }
        except Exception as e:
            return {"error": str(e)}
    
    async def _rpc_call(self, method: str, params: list) -> dict:
        """Make Solana RPC call."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(SOLANA_RPC, json=payload) as resp:
                return await resp.json()


bot = WattCoinBot()


@client.event
async def on_ready():
    """Bot startup."""
    print(f'✅ Logged in as {client.user}')
    # Sync slash commands
    await tree.sync()
    # Start background alert task
    check_alerts.start()


@tree.command(name="balance", description="Query WATT token balance")
@app_commands.describe(wallet="Solana wallet address")
async def balance_command(interaction: discord.Interaction, wallet: str):
    """/balance <wallet> - Get WATT balance."""
    await interaction.response.defer()
    
    result = await bot.get_watt_balance(wallet)
    
    if result['success']:
        embed = discord.Embed(
            title="💰 WATT Balance",
            description=f"Wallet: `{wallet[:20]}...`",
            color=discord.Color.green()
        )
        embed.add_field(name="Balance", value=f"**{result['balance']:,} WATT**")
        embed.set_footer(text="Data from Solana Mainnet")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(
            f"❌ Error: {result['error']}", ephemeral=True
        )


@tree.command(name="stats", description="Show WattCoin network statistics")
async def stats_command(interaction: discord.Interaction):
    """/stats - Get network stats."""
    await interaction.response.defer()
    
    stats = await bot.get_network_stats()
    
    embed = discord.Embed(
        title="📊 WattCoin Network Stats",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Active Nodes", value=stats.get('active_nodes', 'N/A'), inline=True)
    embed.add_field(name="Total Tasks", value=stats.get('total_tasks', 'N/A'), inline=True)
    embed.add_field(name="Pending Bounties", value=stats.get('pending_bounties', 'N/A'), inline=True)
    
    await interaction.followup.send(embed=embed)


@tree.command(name="alerts", description="Toggle WattCoin network alerts")
@app_commands.describe(action="Enable or disable alerts")
@app_commands.choices(action=[
    app_commands.Choice(name="Enable", value="on"),
    app_commands.Choice(name="Disable", value="off")
])
async def alerts_command(interaction: discord.Interaction, action: str):
    """/alerts [on|off] - Toggle alerts."""
    channel_id = interaction.channel_id
    
    if action == 'on':
        alert_channels.add(channel_id)
        await interaction.response.send_message(
            "✅ Alerts enabled for this channel. You'll receive network notifications.",
            ephemeral=True
        )
    else:
        alert_channels.discard(channel_id)
        await interaction.response.send_message(
            "✅ Alerts disabled for this channel.",
            ephemeral=True
        )


@tasks.loop(minutes=5)
async def check_alerts():
    """Background task: Check for network events and send alerts."""
    if not alert_channels:
        return
    
    try:
        # Check network status (simplified)
        new_stats = await bot.get_network_stats()
        
        # Compare with cache and send alerts if significant changes
        if network_cache and 'active_nodes' in new_stats:
            old_nodes = network_cache.get('active_nodes', 0)
            new_nodes = new_stats.get('active_nodes', 0)
            
            if abs(new_nodes - old_nodes) > 5:  # Significant change
                for channel_id in alert_channels:
                    channel = client.get_channel(channel_id)
                    if channel:
                        await channel.send(
                            f"🔔 **Network Alert**: Active nodes changed from {old_nodes} to {new_nodes}"
                        )
        
        network_cache.update(new_stats)
        
    except Exception as e:
        print(f"Alert check error: {e}")


@check_alerts.before_loop
async def before_alerts():
    await client.wait_until_ready()


if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("❌ Set DISCORD_TOKEN environment variable")
        exit(1)
    
    client.run(DISCORD_TOKEN)
