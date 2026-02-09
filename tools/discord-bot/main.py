import discord
from discord.ext import commands, tasks
import asyncio
import logging
from config import DISCORD_BOT_TOKEN, DISCORD_ALERTS_CHANNEL, EMBED_COLOR
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
        self.last_activity_id = None # To track seen alerts

    async def setup_hook(self):
        await self.load_extension('cogs.commands')
        logger.info("Cog loaded: commands")
        await self.tree.sync()
        logger.info("Slash commands synced")
        self.alert_task.start()

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')

    @tasks.loop(seconds=60)
    async def alert_task(self):
        if not DISCORD_ALERTS_CHANNEL:
            return

        channel = self.get_channel(DISCORD_ALERTS_CHANNEL)
        if not channel:
            # Try to fetch if not in cache
            try:
                channel = await self.fetch_channel(DISCORD_ALERTS_CHANNEL)
            except:
                logger.error(f"Could not find alerts channel with ID {DISCORD_ALERTS_CHANNEL}")
                return

        try:
            activities = await self.api.get_alerts()
            if not activities:
                return

            # Sort activities by timestamp or ID to process in order
            # Assuming activities is a list of dicts with 'id' and 'type'
            new_activities = []
            if self.last_activity_id is None:
                # First run, just set the last ID to the latest one
                if activities:
                    self.last_activity_id = activities[0].get('id')
                return

            for act in activities:
                if act.get('id') == self.last_activity_id:
                    break
                new_activities.append(act)

            if not new_activities:
                return

            # Update last activity ID
            self.last_activity_id = activities[0].get('id')

            # Process new activities (in reverse to post oldest first)
            for act in reversed(new_activities):
                embed = self.format_activity_embed(act)
                if embed:
                    await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in alert task: {e}")

    def format_activity_embed(self, act):
        act_type = act.get('type')
        title = "New Activity"
        description = act.get('description', 'No details available.')
        
        if act_type == 'NEW_BOUNTY':
            title = "🆕 New Bounty Available!"
        elif act_type == 'PR_MERGED':
            title = "✅ Pull Request Merged"
        elif act_type == 'NEW_SOLUTION':
            title = "💡 New Solution Submitted"
        elif act_type == 'TIER_PROMOTION':
            title = "🏆 Tier Promotion!"
        
        embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        if 'url' in act:
            embed.url = act['url']
        
        return embed

    @alert_task.before_loop
    async def before_alert_task(self):
        await self.wait_until_ready()

if __name__ == "__main__":
    bot = WattBot()
    bot.run(DISCORD_BOT_TOKEN)
