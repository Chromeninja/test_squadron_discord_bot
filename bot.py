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
from helpers.views import VerificationView
from helpers.rate_limiter import cleanup_attempts
from helpers.logger import get_logger
from helpers.database import Database
from helpers.task_queue import start_task_workers, task_queue

# Initialize logger
logger = get_logger(__name__)

# Load environment variables
load_dotenv()

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()

# Load sensitive information from .env
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    logger.critical("DISCORD_TOKEN not found in environment variables.")
    raise ValueError("DISCORD_TOKEN not set.")

# Access configuration values from config.yaml
PREFIX = config['bot']['prefix']
VERIFICATION_CHANNEL_ID = config['channels']['verification_channel_id']
BOT_VERIFIED_ROLE_ID = config['roles']['bot_verified_role_id']
MAIN_ROLE_ID = config['roles']['main_role_id']
AFFILIATE_ROLE_ID = config['roles']['affiliate_role_id']
NON_MEMBER_ROLE_ID = config['roles']['non_member_role_id']
BOT_ADMIN_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('bot_admins', [])]
LEAD_MODERATOR_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('lead_moderators', [])]

intents = discord.Intents.default()
intents.guilds = True  # Needed for guild-related events
intents.members = True  # Needed for member-related events
intents.message_content = True  # Needed for reading message content
intents.voice_states = True  # Needed for voice state updates
intents.presences = True # Needed for member presence updates

# List of initial extensions to load
initial_extensions = [
    'cogs.verification',
    'cogs.admin',
    'cogs.voice'
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

        # Assign the entire config to the bot instance
        self.config = config

        # Pass role and channel IDs to the bot for use in cogs
        self.VERIFICATION_CHANNEL_ID = VERIFICATION_CHANNEL_ID
        self.BOT_VERIFIED_ROLE_ID = BOT_VERIFIED_ROLE_ID
        self.MAIN_ROLE_ID = MAIN_ROLE_ID
        self.AFFILIATE_ROLE_ID = AFFILIATE_ROLE_ID
        self.NON_MEMBER_ROLE_ID = NON_MEMBER_ROLE_ID
        self.BOT_ADMIN_ROLE_IDS = BOT_ADMIN_ROLE_IDS
        self.LEAD_MODERATOR_ROLE_IDS = LEAD_MODERATOR_ROLE_IDS

        # Initialize uptime tracking
        self.start_time = time.monotonic()

        # Initialize the HTTP client
        self.http_client = HTTPClient()

        # Initialize role cache
        self.role_cache = {}

    async def setup_hook(self):
        """
        Asynchronously loads all initial extensions (cogs) and syncs commands.
        """
        # Initialize the database
        await Database.initialize()
        
        # Start the task queue workers
        await start_task_workers(num_workers=2)  # Adjust the number of workers as needed
        
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

        # Register the persistent VerificationView
        self.add_view(VerificationView(self))

        # Sync the command tree after loading all cogs
        try:
            await self.tree.sync()
            logger.info("All commands synced globally.")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

        # Set command permissions for each guild
        for guild in self.guilds:
            await self.set_admin_command_permissions(guild)

    async def on_ready(self):
        """
        Event handler for when the bot is ready and connected to Discord.
        """
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is ready and online!")
        
        for guild in self.guilds:
            await self.check_bot_permissions(guild)

    async def check_bot_permissions(self, guild: discord.Guild):
        """
        Checks if the bot has all the required permissions in the specified guild.
        Logs a warning if permissions are missing.
        """
        required_permissions = [
            "manage_roles",            # To assign/remove roles during verification and admin commands
            "manage_channels",         # To create/edit/delete voice channels
            "change_nickname",         # To change the bot's nickname
            "manage_nicknames",        # To change user nicknames during verification
            "view_channel",            # To view channels for verification and commands
            "send_messages",           # To send messages in channels
            "embed_links",             # To send rich embed messages
            "read_message_history",    # To fetch historical messages for verification
            "use_application_commands",# To enable slash commands
            "connect",                 # To join voice channels
            "move_members",            # To move members between voice channels
        ]

        if not guild or not guild.me:
            logger.warning("Bot permissions cannot be checked because the bot is not in the guild or the guild is None.")
            return

        bot_member = guild.me
        missing_permissions = [
            perm for perm in required_permissions 
            if not getattr(bot_member.guild_permissions, perm, False)
        ]

        if missing_permissions:
            logger.warning(
                f"Missing permissions in guild '{guild.name}': {', '.join(missing_permissions)}"
            )
        else:
            logger.info(f"All required permissions are present in guild '{guild.name}'.")

    async def cache_roles(self):
        """
        Caches role objects to avoid redundant lookups.
        """
        await self.wait_until_ready()
        if not self.guilds:
            logger.warning("Bot is not in any guild. Skipping role cache.")
            return
        
        guild = self.guilds[0]
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

    async def set_admin_command_permissions(self, guild: discord.Guild):
        """
        Applies slash command permissions so only 'bot_admins' or 'lead_moderators' can see/use certain commands.
        """
        # Define the restricted commands and combine role IDs
        restricted_commands = ["reset-all", "reset-user", "status", "view-logs"]
        combined_role_ids = set(self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS)

        # Generate permissions for the roles
        permissions = [
            discord.AppCommandPermission(
                type=discord.AppCommandPermissionType.ROLE,
                id=role_id,
                permission=True
            )
            for role_id in combined_role_ids
        ]

        # Apply permissions to each command
        for cmd_name in restricted_commands:
            command = self.tree.get_command(cmd_name, guild=guild)
            if command:
                try:
                    await self.tree.set_permissions(guild, command, permissions)
                    logger.info(f"Permissions set for command '{cmd_name}' in guild '{guild.name}'.")
                except discord.HTTPException as e:
                    logger.error(f"Failed to set permissions for '{cmd_name}' in guild '{guild.name}': {e}")
            else:
                logger.warning(f"Command '{cmd_name}' not found in guild '{guild.name}'. Skipping.")


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

        # Enqueue shutdown signals for workers
        for _ in range(2):  # Number of workers started
            await task_queue.put(None)

        await task_queue.join()  # Wait until all tasks are processed

        # Close the HTTP client
        await self.http_client.close()
        await super().close()

# Initialize the bot
bot = MyBot(command_prefix=PREFIX, intents=intents)

# Run the bot
bot.run(TOKEN)
