# bot.py

import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv
import asyncio
import time

from config.config_loader import ConfigLoader
from helpers.http_helper import HTTPClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)

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
    logging.critical("DISCORD_TOKEN not found in environment variables.")
    raise ValueError("DISCORD_TOKEN not set.")

# Initialize bot intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Needed for receiving messages

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

    async def setup_hook(self):
        """
        Asynchronously loads all initial extensions (cogs).
        """
        # Initialize the HTTP client session
        await self.http_client.init_session()

        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                logging.info(f"Loaded extension: {extension}")
            except Exception as e:
                logging.error(f"Failed to load extension {extension}: {e}")

    async def on_ready(self):
        """
        Event handler for when the bot is ready and connected to Discord.
        """
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logging.info("Bot is ready and online!")

        # Sync the command tree globally
        try:
            synced = await self.tree.sync()
            logging.info(f"Synced {len(synced)} commands globally.")
        except Exception as e:
            logging.error(f"Failed to sync commands: {e}")

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
        logging.info("Shutting down the bot and closing HTTP client session.")
        await self.http_client.close()
        await super().close()


bot = MyBot(command_prefix=PREFIX, intents=intents)
bot.run(TOKEN)
