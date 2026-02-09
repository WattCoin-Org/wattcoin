import discord
from discord.ext import commands
from discord import app_commands
from api_client import WattCoinAPI, DexScreenerAPI
from solana_client import SolanaClient
from config import EMBED_COLOR
from solders.pubkey import Pubkey
import logging

logger = logging.getLogger('wattcoin-bot')

class WattCoinCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = WattCoinAPI()
        self.dex = DexScreenerAPI()
        self.solana = SolanaClient()

    @app_commands.command(name="balance", description="Check WATT balance of a Solana address")
    async def balance(self, interaction: discord.Interaction, address: str):
        await interaction.response.defer()
        
        # Validate Solana address
        try:
            Pubkey.from_string(address)
        except ValueError:
            await interaction.followup.send("❌ Invalid Solana address format. Please provide a valid public key.", ephemeral=True)
            return

        try:
            balance = await self.solana.get_watt_balance(address)
            
            if balance is None:
                await interaction.followup.send("❌ Could not fetch balance. Please try again later.", ephemeral=True)
                return

            embed = discord.Embed(
                title="WATT Balance",
                description=f"Address: `{address}`",
                color=EMBED_COLOR
            )
            embed.add_field(name="Balance", value=f"{balance:,.2f} WATT")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in balance command: {e}")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    @app_commands.command(name="price", description="Get current WATT price from DexScreener")
    async def price(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            pair_data = await self.dex.get_price()
            
            if not pair_data:
                await interaction.followup.send("❌ Could not fetch price data.")
                return

            embed = discord.Embed(title="WATT Price Stats", color=EMBED_COLOR)
            embed.add_field(name="Price (USD)", value=f"${pair_data.get('priceUsd', 'N/A')}")
            embed.add_field(name="24h Change", value=f"{pair_data.get('priceChange', {}).get('h24', 'N/A')}%")
            embed.add_field(name="Volume (24h)", value=f"${pair_data.get('volume', {}).get('h24', 0):,.2f}")
            embed.add_field(name="Liquidity", value=f"${pair_data.get('liquidity', {}).get('usd', 0):,.2f}")
            embed.set_footer(text=f"Pair: {pair_data.get('pairAddress')}")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in price command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching price.")

    @app_commands.command(name="bounties", description="List active WattCoin bounties")
    async def bounties(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            bounties = await self.api.get_bounties()
            
            embed = discord.Embed(title="Active Bounties", color=EMBED_COLOR)
            if not bounties:
                embed.description = "No active bounties found."
            else:
                for b in bounties[:10]: # Limit to 10
                    embed.add_field(
                        name=b.get('title', 'Untitled'),
                        value=f"Reward: {b.get('reward', 'N/A')} WATT\n[View Bounty]({b.get('url', '#')})",
                        inline=False
                    )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in bounties command: {e}")
            await interaction.followup.send("❌ Failed to fetch bounties.")

    @app_commands.command(name="tasks", description="List available tasks")
    async def tasks(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            tasks = await self.api.get_tasks()
            
            embed = discord.Embed(title="Available Tasks", color=EMBED_COLOR)
            if not tasks:
                embed.description = "No tasks available."
            else:
                for t in tasks[:10]:
                    embed.add_field(
                        name=t.get('name', 'Unnamed Task'),
                        value=f"Type: {t.get('type', 'N/A')}\nPoints: {t.get('points', 0)}",
                        inline=False
                    )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in tasks command: {e}")
            await interaction.followup.send("❌ Failed to fetch tasks.")

    @app_commands.command(name="stats", description="View WattCoin ecosystem statistics")
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            stats = await self.api.get_stats()
            
            if not stats:
                await interaction.followup.send("❌ Could not fetch stats.")
                return

            embed = discord.Embed(title="WattCoin Stats", color=EMBED_COLOR)
            embed.add_field(name="Total Users", value=f"{stats.get('total_users', 0):,}")
            embed.add_field(name="Total Bounties", value=f"{stats.get('total_bounties', 0):,}")
            embed.add_field(name="Total Paid", value=f"{stats.get('total_paid', 0):,.0f} WATT")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await interaction.followup.send("❌ Failed to fetch stats.")

    @app_commands.command(name="leaderboard", description="View top contributors")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            lb = await self.api.get_leaderboard()
            
            embed = discord.Embed(title="WattCoin Leaderboard", color=EMBED_COLOR)
            if not lb:
                embed.description = "Leaderboard is empty."
            else:
                description = ""
                for i, entry in enumerate(lb[:10], 1):
                    description += f"{i}. **{entry.get('username', 'Anonymous')}**: {entry.get('score', 0):,} pts\n"
                embed.description = description
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            await interaction.followup.send("❌ Failed to fetch leaderboard.")

async def setup(bot):
    await bot.add_cog(WattCoinCommands(bot))
