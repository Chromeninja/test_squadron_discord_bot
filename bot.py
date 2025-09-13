# Bot.py

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
VERIFICATION_CHANNEL_ID = config["channels"]["verification_channel_id"]
BOT_SPAM_CHANNEL_ID = config["channels"].get("bot_spam_channel_id")
BOT_VERIFIED_ROLE_ID = config["roles"]["bot_verified_role_id"]
MAIN_ROLE_ID = config["roles"]["main_role_id"]
AFFILIATE_ROLE_ID = config["roles"]["affiliate_role_id"]
NON_MEMBER_ROLE_ID = config["roles"]["non_member_role_id"]
BOT_ADMIN_ROLE_IDS = [int(role_id) for role_id in config["roles"].get("bot_admins", [])]
LEAD_MODERATOR_ROLE_IDS = [
    int(role_id) for role_id in config["roles"].get("lead_moderators", [])
]

intents = discord.Intents.default()
intents.guilds = True  # Needed for guild-related events
intents.members = True  # Needed for member-related events
intents.message_content = True  # Needed for reading message content
intents.voice_states = True  # Needed for voice state updates
intents.presences = True  # Needed for member presence updates

# List of initial extensions to load
initial_extensions = [
    "cogs.verification.commands",
    "cogs.admin.commands",
    "cogs.admin.recheck",
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

        # Pass role and channel IDs to the bot for use in cogs
        self.VERIFICATION_CHANNEL_ID = VERIFICATION_CHANNEL_ID
        self.BOT_SPAM_CHANNEL_ID = BOT_SPAM_CHANNEL_ID
        self.BOT_VERIFIED_ROLE_ID = BOT_VERIFIED_ROLE_ID
        self.MAIN_ROLE_ID = MAIN_ROLE_ID
        self.AFFILIATE_ROLE_ID = AFFILIATE_ROLE_ID
        self.NON_MEMBER_ROLE_ID = NON_MEMBER_ROLE_ID
        self.BOT_ADMIN_ROLE_IDS = BOT_ADMIN_ROLE_IDS
        self.LEAD_MODERATOR_ROLE_IDS = LEAD_MODERATOR_ROLE_IDS

        # Initialize uptime tracking
        self.start_time = time.monotonic()

        # Initialize the HTTP client with configurable user-agent (falls back internally)
        rsi_cfg = (self.config or {}).get("rsi", {}) or {}
        ua = rsi_cfg.get("user_agent")
        self.http_client = HTTPClient(user_agent=ua)

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

        # Set command permissions for each guild (always attempt regardless of sync result)
        for guild in self.guilds:
            await self.set_admin_command_permissions(guild)

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
        """Cache commonly used Role objects from the first guild."""
        await self.wait_until_ready()
        if not self.guilds:
            logger.warning("Bot is not in any guild. Skipping role cache.")
            return

        guild = self.guilds[0]
        role_ids = [
            self.BOT_VERIFIED_ROLE_ID,
            self.MAIN_ROLE_ID,
            self.AFFILIATE_ROLE_ID,
            self.NON_MEMBER_ROLE_ID,
        ]
        for role_id in role_ids:
            if role := guild.get_role(role_id):
                self.role_cache[role_id] = role
            else:
                # Persist suppression across restarts: only WARN the first time
                # Across all runs unless DB entry is cleared.
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
                        # Non-fatal: if DB write fails, continue but don't raise
                        logger.debug(
                            "Failed to persist missing-role warning for guild %s",
                            guild.id,
                        )
                else:
                    logger.info(
                        f"Role with ID {role_id} not found in guild '{guild.name}' (already reported)."
                    )

    async def set_admin_command_permissions(self, guild: discord.Guild) -> None:
        """Attempt per-command role permissions; fall back to runtime checks."""

        # Define the restricted commands and combine role IDs
        restricted_commands = [
            "reset-all",
            "reset-user",
            "status",
            "view-logs",
            "recheck-user",
        ]
        combined_role_ids = set(self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS)

        # Build list of configured role IDs that exist in this guild; log missing.
        valid_roles = []
        for role_id in combined_role_ids:
            if guild.get_role(role_id):
                valid_roles.append(role_id)
            else:
                # Missing configured role is not fatal; log for operator visibility.
                try:
                    reported = await Database.has_reported_missing_roles(guild.id)
                except Exception:
                    reported = False
                if not reported and guild.id not in self._missing_role_warned_guilds:
                    logger.warning(
                        f"Configured role ID {role_id} not found in guild '{guild.name}'."
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
                        f"Configured role ID {role_id} not found in guild '{guild.name}' (already reported)."
                    )

                    # If there are no valid role IDs, nothing to apply. The runtime checks still protect commands.
        if not valid_roles:
            logger.info(
                f"No valid configured admin/lead-moderator roles present in guild '{guild.name}'. "
                "Skipping App Command permission setup and relying on runtime checks."
            )
            return

            # Only attempt App Command permission flow if the discord module and tree
            # Expose the required API. In many runtime environments this API is not
            # Present; in that case we skip attempting to set per-command permissions
            # And rely on runtime decorator checks instead. This avoids noisy warnings
            # During normal operation.
        if not (
            hasattr(discord, "AppCommandPermission")
            and hasattr(discord, "AppCommandPermissionType")
            and hasattr(self.tree, "set_permissions")
        ):
            logger.info(
                "Per-command App Command permission API not available in this environment; "
                "skipping and relying on runtime decorator checks."
            )
            return

        try:
            permissions = [
                discord.AppCommandPermission(
                    type=discord.AppCommandPermissionType.ROLE,
                    id=role_id,
                    permission=True,
                )
                for role_id in valid_roles
            ]

            for cmd_name in restricted_commands:
                if command := self.tree.get_command(cmd_name, guild=guild):
                    try:
                        # Older discord.py: tree.set_permissions(guild, command, permissions)
                        await self.tree.set_permissions(guild, command, permissions)
                        logger.info(
                            f"App Command permissions set for '{cmd_name}' in guild '{guild.name}'."
                        )
                    except discord.HTTPException as e:
                        # Discord may reject the operation; log at INFO and continue
                        logger.info(
                            f"Discord rejected App Command permission update for '{cmd_name}' "
                            f"in guild '{guild.name}': {e}. Continuing with runtime checks."
                        )
                else:
                    logger.debug(
                        f"Command '{cmd_name}' not found in guild '{guild.name}'."
                    )
        except Exception as e:
            # Catch-all: don't let permission setup break bot startup.
            logger.info(
                f"Failed to set App Command permissions in guild '{guild.name}': {e}. "
                + "Using runtime decorator checks instead."
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

    async def has_admin_permissions(self, user: discord.Member) -> bool:
        """
        Check if a user has admin permissions based on configured roles.

        Args:
            user: Discord member to check

        Returns:
            bool: True if user has bot admin or lead moderator roles
        """
        if not isinstance(user, discord.Member):
            return False

        user_role_ids = [role.id for role in user.roles]
        admin_role_ids = set(self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS)

        return any(role_id in admin_role_ids for role_id in user_role_ids)

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

# Only auto-run if not in explicit dry-run context (dev_smoke_startup sets TESTBOT_DRY_RUN)
if os.getenv("TESTBOT_DRY_RUN") != "1":
    bot.run(TOKEN)
