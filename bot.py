# bot.py

import discord
from discord.ext import commands
import os
import asyncio
import time
from dotenv import load_dotenv

from config.config_loader import ConfigLoader
from helpers.http_helper import HTTPClient
from helpers.token_manager import cleanup_tokens
from helpers.rate_limiter import cleanup_attempts
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Load environment variables
load_dotenv()

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()

# Load sensitive information from .env
TOKEN = os.getenv('DISCORD_TOKEN')

# Access configuration values from config.yaml
PREFIX = config['bot']['prefix']
VERIFICATION_CHANNEL_ID = config['channels']['verification_channel_id']
BOT_VERIFIED_ROLE_ID = config['roles']['bot_verified_role_id']
MAIN_ROLE_ID = config['roles']['main_role_id']
AFFILIATE_ROLE_ID = config['roles']['affiliate_role_id']
NON_MEMBER_ROLE_ID = config['roles']['non_member_role_id']

if not TOKEN:
    logger.critical("DISCORD_TOKEN not found in environment variables.")
    raise ValueError("DISCORD_TOKEN not set.")

# Initialize bot intents
intents = discord.Intents.default()
intents.guilds = True  # Needed for guild-related events
intents.members = True  # Needed for member-related events
intents.message_content = True  # Needed for reading message content

# List of initial extensions to load
initial_extensions = [
    'cogs.verification',
    'cogs.admin'
]

class MyBot(commands.Bot):
    """
    Custom Bot class extending commands.Bot to include additional attributes.
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes the MyBot instance with specific role and channel IDs.
        """
        super().__init__(*args, **kwargs)

        # Pass role and channel IDs to the bot for use in cogs
        self.VERIFICATION_CHANNEL_ID = VERIFICATION_CHANNEL_ID
        self.BOT_VERIFIED_ROLE_ID = BOT_VERIFIED_ROLE_ID
        self.MAIN_ROLE_ID = MAIN_ROLE_ID
        self.AFFILIATE_ROLE_ID = AFFILIATE_ROLE_ID
        self.NON_MEMBER_ROLE_ID = NON_MEMBER_ROLE_ID

        # Initialize uptime tracking
        self.start_time = time.monotonic()

        # Initialize the HTTP client
        self.http_client = HTTPClient()

        # Initialize role cache
        self.role_cache = {}

    async def setup_hook(self):
        """
        Asynchronously loads all initial extensions (cogs).
        """
        # Initialize the HTTP client session
        await self.http_client.init_session()

        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}")

        # Cache roles after bot is ready
        self.loop.create_task(self.cache_roles())

        # Start cleanup tasks
        self.loop.create_task(self.token_cleanup_task())
        self.loop.create_task(self.attempts_cleanup_task())

    async def cache_roles(self):
        """
        Caches role objects to avoid redundant lookups.
        """
        await self.wait_until_ready()
        guild = discord.utils.get(self.guilds)  # Assuming bot is in only one guild
        role_ids = [
            self.BOT_VERIFIED_ROLE_ID,
            self.MAIN_ROLE_ID,
            self.AFFILIATE_ROLE_ID,
            self.NON_MEMBER_ROLE_ID
        ]
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role:
                self.role_cache[role_id] = role
            else:
                logger.warning(f"Role with ID {role_id} not found in guild '{guild.name}'.")

    async def token_cleanup_task(self):
        """
        Periodically cleans up expired tokens.
        """
        while not self.is_closed():
            await asyncio.sleep(600)  # Run every 10 minutes
            cleanup_tokens()
            logger.debug("Expired tokens cleaned up.")

    async def attempts_cleanup_task(self):
        """
        Periodically cleans up expired rate-limiting data.
        """
        while not self.is_closed():
            await asyncio.sleep(600)  # Run every 10 minutes
            cleanup_attempts()
            logger.debug("Expired rate-limiting data cleaned up.")

    async def on_ready(self):
        """
        Event handler for when the bot is ready and connected to Discord.
        """
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is ready and online!")

        # Sync the command tree globally
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} commands globally.")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    @property
    def uptime(self) -> str:
        """
        Calculates the bot's uptime.

        Returns:
            str: The uptime as a formatted string.
        """
        now = time.monotonic()
        delta = int(now - self.start_time)
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    async def close(self):
        """
        Closes the bot and the HTTP client session.
        """
        logger.info("Shutting down the bot and closing HTTP client session.")
        await self.http_client.close()
        await super().close()

# Initialize the bot
bot = MyBot(command_prefix=PREFIX, intents=intents)

# Run the bot
bot.run(TOKEN)
