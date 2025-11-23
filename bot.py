import asyncio
import os
import time

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config.config_loader import ConfigLoader
from helpers.announcement import BulkAnnouncer
from helpers.http_helper import HTTPClient
from helpers.rate_limiter import cleanup_attempts
from helpers.task_queue import start_task_workers, task_queue
from helpers.token_manager import cleanup_tokens
from helpers.views import ChannelSettingsView, VerificationView
from services.db.database import Database
from utils.logging import get_logger
from utils.tasks import spawn

# Initialize logger
logger = get_logger(__name__)

# Load environment variables
load_dotenv()

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()

# Load sensitive information from .env
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    logger.critical("DISCORD_TOKEN not found in environment variables.")
    raise ValueError("DISCORD_TOKEN not set.")

# Access configuration values from config.yaml (kept at module scope so dev tools can import PREFIX safely)
# Some deployments may accidentally supply an empty list / string; fall back to mention‑only behavior.
raw_prefix = config["bot"].get("prefix")
PREFIX = (
    raw_prefix if raw_prefix else commands.when_mentioned
)  # empty list, empty string, None -> default

# Roles and channels are now managed per-guild via the database.
# These legacy constants have been removed; access via bot.services.config at runtime.

# Configure intents - start from none and enable only what's required
intents = discord.Intents.none()
intents.guilds = True  # Required: Guild events, channels, roles
intents.members = True  # Required: Member join/leave, role updates for verification
intents.voice_states = True  # Required: Voice channel join/leave for voice system
# Privileged intents disabled (not required for current features):
# - message_content: Bot uses slash commands, not message commands
# - presences: Not used for core functionality (optional activity display only)

# List of initial extensions to load
initial_extensions = [
    "cogs.verification.commands",
    "cogs.admin.commands",
    "cogs.admin.recheck",
    "cogs.admin.verify_bulk",
    "cogs.voice.commands",
    "cogs.voice.events",
    "cogs.voice.service_bridge",
]


class MyBot(commands.Bot):
    """Bot with project-specific attributes and helpers."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Assign the entire config to the bot instance
        self.config = config

        # Role and channel configuration now accessed via services.config per guild
        # No more bot-level attributes for roles/channels

        # Initialize uptime tracking
        self.start_time = time.monotonic()

        # Initialize the HTTP client with configurable user-agent (falls back internally)
        rsi_cfg = (self.config or {}).get("rsi", {}) or {}
        ua = rsi_cfg.get("user_agent")
        # Reduce concurrency to avoid rate limiting from RSI website
        self.http_client = HTTPClient(user_agent=ua, concurrency=3, timeout=20)

        # Initialize role cache and warning tracking
        self.role_cache = {}
        self._missing_role_warned_guilds = set()

    async def setup_hook(self) -> None:
        """Load cogs, initialize services, and sync commands."""
        # Initialize the database
        await Database.initialize()

        # Initialize services container
        from services.service_container import ServiceContainer

        self.services = ServiceContainer(self)
        await self.services.initialize()
        logger.info("ServiceContainer initialized")

        # Start internal API server for web dashboard
        try:
            from services.internal_api import InternalAPIServer

            self.internal_api = InternalAPIServer(self.services)
            await self.internal_api.start()
        except Exception as e:
            logger.exception("Failed to start internal API server", exc_info=e)
            # Don't fail bot startup if internal API fails
            self.internal_api = None

        # Run application-driven voice data migration (safe, idempotent)
        try:
            from helpers.voice_migration import run_voice_data_migration

            await run_voice_data_migration(self)
        except Exception as e:
            logger.exception("Voice data migration failed", exc_info=e)

        # Add the BulkAnnouncer cog after DB is initialized
        await self.add_cog(BulkAnnouncer(self))

        # Start the task queue workers
        await start_task_workers(
            num_workers=2
        )  # Adjust the number of workers as needed

        # Initialize the HTTP client session
        # We use _get_session to ensure the HTTP client is initialized
        await self.http_client._get_session()

        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.exception(f"Failed to load extension {extension}", exc_info=e)

        # Cache roles after bot is ready
        spawn(self.cache_roles())

        # Start cleanup tasks
        spawn(self.token_cleanup_task())
        spawn(self.attempts_cleanup_task())

        # Register persistent views (must happen every startup for persistence to work)
        self.add_view(VerificationView(self))
        self.add_view(ChannelSettingsView(self))

        # Sync the command tree after loading all cogs
        try:
            await self.tree.sync()
            logger.info("All commands synced globally.")
        except Exception as e:
            logger.exception("Failed to sync commands", exc_info=e)

        # Log all loaded commands after the setup (deterministic ordering)
        logger.info("Registered commands: ")
        for command in self.tree.walk_commands():
            logger.info(
                f"- Command: {command.name}, Description: {command.description}"
            )

    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is ready and online!")
        for guild in self.guilds:
            try:
                await guild.chunk(cache=True)
                logger.info(f"Chunked members for guild '{guild.name}' ({guild.id})")
            except Exception as e:
                logger.warning(f"Could not chunk members for guild '{guild.name}': {e}")
        for guild in self.guilds:
            await self.check_bot_permissions(guild)

        # Run legacy settings migration after bot is ready and guilds are loaded
        if hasattr(self, "services") and self.services.config:
            try:
                await self.services.config.maybe_migrate_legacy_settings(self)
            except Exception as e:
                logger.exception("Legacy settings migration failed", exc_info=e)

    async def check_bot_permissions(self, guild: discord.Guild) -> None:
        """Verify required guild-level permissions and log any missing ones."""
        required_permissions = [
            "manage_roles",
            "manage_channels",
            "change_nickname",
            "manage_nicknames",
            "view_channel",
            "send_messages",
            "embed_links",
            "read_message_history",
            "use_application_commands",
            "connect",
            "move_members",
        ]

        if not guild or not guild.me:
            logger.warning(
                "Bot permissions cannot be checked because the bot is not in the guild or the guild is None."
            )
            return

        bot_member = guild.me
        if missing_permissions := [
            perm
            for perm in required_permissions
            if not getattr(bot_member.guild_permissions, perm, False)
        ]:
            logger.warning(
                f"Missing permissions in guild '{guild.name}': {', '.join(missing_permissions)}"
            )
        else:
            logger.info(
                f"All required permissions are present in guild '{guild.name}'."
            )

    async def cache_roles(self) -> None:
        """Cache commonly used Role objects from all guilds based on DB config."""
        await self.wait_until_ready()
        if not self.guilds:
            logger.warning("Bot is not in any guild. Skipping role cache.")
            return

        if not hasattr(self, "services") or not self.services or not self.services.config:
            logger.warning("Services not initialized yet. Skipping role cache.")
            return

        for guild in self.guilds:
            try:
                roles_config = await self.services.config.get_guild_roles(guild.id)
                role_ids = [
                    roles_config.get("bot_verified_role_id"),
                    roles_config.get("main_role_id"),
                    roles_config.get("affiliate_role_id"),
                    roles_config.get("non_member_role_id"),
                ]
                
                for role_id in role_ids:
                    if not role_id:
                        continue
                    if role := guild.get_role(int(role_id)):
                        self.role_cache[role_id] = role
                    else:
                        # Only warn once per guild
                        try:
                            reported = await Database.has_reported_missing_roles(guild.id)
                        except Exception:
                            reported = False
                        if not reported and guild.id not in self._missing_role_warned_guilds:
                            logger.warning(
                                f"Role with ID {role_id} not found in guild '{guild.name}'."
                            )
                            self._missing_role_warned_guilds.add(guild.id)
                            try:
                                await Database.mark_reported_missing_roles(guild.id)
                            except Exception:
                                logger.debug(
                                    "Failed to persist missing-role warning for guild %s",
                                    guild.id,
                                )
                        else:
                            logger.info(
                                f"Role {role_id} missing in '{guild.name}' "
                                "(already reported)."
                            )
            except Exception as e:
                logger.warning(
                    f"Failed to cache roles for guild '{guild.name}': {e}"
                )

    async def token_cleanup_task(self) -> None:
        """
        Periodically cleans up expired tokens.
        """
        while not self.is_closed():
            await asyncio.sleep(600)  # Run every 10 minutes
            cleanup_tokens()
            logger.debug("Expired tokens cleaned up.")

    async def attempts_cleanup_task(self) -> None:
        """
        Periodically cleans up expired rate-limiting data.
        """
        while not self.is_closed():
            await asyncio.sleep(600)  # Run every 10 minutes
            # Cleanup_attempts is an async coroutine; await it to avoid "coroutine was never awaited" warnings
            await cleanup_attempts()

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

    async def has_admin_permissions(
        self,
        user: discord.Member,
        guild: discord.Guild | None = None,
    ) -> bool:
        """
        Check if a user has admin permissions based on configured roles or privileged status.

        Args:
            user: Discord member to check
            guild: Optional guild context (provided by slash-command decorators)

        Returns:
            bool: True if user has bot admin, lead moderator roles, is bot owner, or has Discord admin
        """
        if not isinstance(user, discord.Member):
            return False

        # Use the privileged user check which includes all fallbacks
        from helpers.permissions_helper import is_privileged_user
        return await is_privileged_user(self, user)

    async def get_guild_config(self, guild_id: int) -> dict:
        """
        Get configuration for a specific guild using the services container.

        Args:
            guild_id: Discord guild ID

        Returns:
            dict: Guild configuration data
        """
        if not hasattr(self, "services") or not self.services.config:
            return {}

        config_service = self.services.config

        # Get common guild settings
        jtc_channels = await config_service.get_join_to_create_channels(guild_id)
        voice_category = await config_service.get_guild_setting(
            guild_id, "voice_category_id"
        )

        # Get roles configuration
        roles = await config_service.get_guild_roles(guild_id)

        # Get channels configuration
        channels = await config_service.get_guild_channels(guild_id)

        return {
            "guild_id": guild_id,
            "join_to_create_channels": jtc_channels,
            "voice_category_id": voice_category,
            "roles": roles,
            "channels": channels,
        }

    async def close(self) -> None:
        """
        Closes the bot and cleans up all resources.
        """
        logger.info("Shutting down the bot and closing HTTP client session.")

        # Stop internal API server if running
        if hasattr(self, 'internal_api') and self.internal_api:
            try:
                await self.internal_api.stop()
                logger.info("Internal API server stopped")
            except Exception as e:
                logger.exception("Error stopping internal API server", exc_info=e)

        # Cleanup services
        if hasattr(self, 'services') and self.services:
            try:
                await self.services.cleanup()
                logger.info("Services cleaned up")
            except Exception as e:
                logger.exception("Error cleaning up services", exc_info=e)

        # Enqueue shutdown signals for task workers
        for _ in range(2):  # Number of workers started
            await task_queue.put(None)

        await task_queue.join()  # Wait until all tasks are processed

        # Close the HTTP client
        await self.http_client.close()

        # Call parent close
        await super().close()

        # Initialize the bot


bot = MyBot(command_prefix=PREFIX, intents=intents)

# Only auto-run if not in explicit dry-run context (dev_smoke_startup sets TESTBOT_DRY_RUN)
if os.getenv("TESTBOT_DRY_RUN") != "1":
    bot.run(TOKEN)
