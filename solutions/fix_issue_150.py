import os
import discord
from discord.ext import commands
from solana.rpc.api import Client

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SOLANA_RPC_URL = os.getenv('SOLANA_RPC_URL')

bot = commands.Bot(command_prefix='!')

client = Client(SOLANA_RPC_URL)

balance_data = {}
alerts_data = {}
network_stats_data = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command(name='balance')
async def balance(ctx, wallet_address: str):
    try:
        balance = client.get_balance(wallet_address)['result']['value']
        await ctx.send(f'Balance for {wallet_address}: {balance} lamports')
    except Exception as e:
        await ctx.send(f'Error retrieving balance: {e}')

@bot.command(name='alert')
async def set_alert(ctx, wallet_address: str, threshold: int):
    alerts_data[wallet_address] = threshold
    await ctx.send(f'Alert set for {wallet_address} at {threshold} lamports')

@bot.command(name='network_stats')
async def network_stats(ctx):
    try:
        latest_block = client.get_latest_blockhash()['result']['value']
        await ctx.send(f'Latest Blockhash: {latest_block["blockhash"]}')
    except Exception as e:
        await ctx.send(f'Error retrieving network stats: {e}')

@bot.command(name='submit_pr')
async def submit_pr(ctx, pr_link: str):
    if not pr_link.startswith('https://github.com/'):
        await ctx.send('Invalid PR link.')
        return
    wallet_address = "Your_Solana_Wallet_Address"
    await ctx.send(f'PR submitted: {pr_link}. Solana Wallet: {wallet_address}')

if __name__ == '__main__':
    bot.run(DISCORD_TOKEN)