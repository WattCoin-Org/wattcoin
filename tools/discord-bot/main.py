import discord
from discord.ext import commands
import asyncio
import logging
from config import DISCORD_BOT_TOKEN, EMBED_COLOR
from api_client import WattCoinAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('wattcoin-bot')

class WattBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.api = WattCoinAPI()

    async def setup_hook(self):
        try:
            await self.load_extension('cogs.commands')
            logger.info("Cog loaded: commands")
        except Exception as e:
            logger.error(f"Failed to load extension commands: {e}")

        try:
            await self.tree.sync()
            logger.info("Slash commands synced")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables.")
    else:
        bot = WattBot()
        try:
            bot.run(DISCORD_BOT_TOKEN)
        except Exception as e:
            logger.error(f"Bot failed to start: {e}")
