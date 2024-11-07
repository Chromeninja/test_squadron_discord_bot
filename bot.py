# bot.py

import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()

from config.config_loader import ConfigLoader  # Import the ConfigLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
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

# Define required configuration variables
required_channels = [
    'VERIFICATION_CHANNEL_ID'
]

required_roles = [
    'BOT_VERIFIED_ROLE_ID',
    'MAIN_ROLE_ID',
    'AFFILIATE_ROLE_ID',
    'NON_MEMBER_ROLE_ID'
]

# Validate required channels
for var in required_channels:
    key = var.lower()
    if not config['channels'].get(key):
        logging.critical(f"{var} not found in configuration file.")
        raise ValueError(f"{var} not set in configuration.")

# Validate required roles
for var in required_roles:
    key = var.lower()
    if not config['roles'].get(key):
        logging.critical(f"{var} not found in configuration file.")
        raise ValueError(f"{var} not set in configuration.")

# Initialize bot intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Needed for receiving messages

initial_extensions = ['cogs.verification']

class MyBot(commands.Bot):
    """
    Custom Bot class extending commands.Bot to include additional attributes.
    """
    def __init__(self, *args, **kwargs):
        """
        Initializes the MyBot instance with specific role and channel IDs.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)

        # Pass role and channel IDs to the bot for use in cogs
        self.VERIFICATION_CHANNEL_ID = VERIFICATION_CHANNEL_ID
        self.BOT_VERIFIED_ROLE_ID = BOT_VERIFIED_ROLE_ID
        self.MAIN_ROLE_ID = MAIN_ROLE_ID
        self.AFFILIATE_ROLE_ID = AFFILIATE_ROLE_ID
        self.NON_MEMBER_ROLE_ID = NON_MEMBER_ROLE_ID

    async def setup_hook(self):
        """
        Asynchronously loads all initial extensions (cogs).
        """
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                logging.info(f"Loaded extension: {extension}")
            except Exception as e:
                logging.error(f"Failed to load extension {extension}: {e}")

bot = MyBot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    """
    Event handler for when the bot is ready and connected to Discord.
    """
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logging.info("Bot is ready and online!")

bot.run(TOKEN)
