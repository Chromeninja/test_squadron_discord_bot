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
from services.log_cleanup import LogCleanupService
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
        self._guild_role_expectations: dict[int, set[str]] = {}

    async def setup_hook(self) -> None:
        """Load cogs, initialize services, and sync commands."""
        # Get bot owner ID from application info
        try:
            app_info = await self.application_info()
            if app_info.owner:
                self.owner_id = app_info.owner.id
                logger.info(f"Bot owner detected: {app_info.owner.name} (ID: {self.owner_id})")
            elif app_info.team:
                # If bot is owned by a team, use team owner
                self.owner_id = app_info.team.owner_id
                logger.info(f"Bot owned by team, team owner ID: {self.owner_id}")
            else:
                logger.warning("Could not determine bot owner from application info")
                self.owner_id = None
        except Exception as e:
            logger.exception("Failed to fetch application info for owner detection", exc_info=e)
            self.owner_id = None

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
        spawn(self.role_refresh_task())

        # Start cleanup tasks
        spawn(self.token_cleanup_task())
        spawn(self.attempts_cleanup_task())
        spawn(self.log_cleanup_task())

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

        if (
            not hasattr(self, "services")
            or not self.services
            or not self.services.config
        ):
            logger.warning("Services not initialized yet. Skipping role cache.")
            return

        for guild in self.guilds:
            try:
                await self.refresh_guild_roles(guild.id, source="startup")
            except Exception as e:
                logger.warning(f"Failed to cache roles for guild '{guild.name}': {e}")

    async def refresh_guild_roles(
        self, guild_id: int, source: str | None = None
    ) -> None:
        """Refresh cached discord.Role objects for a single guild."""
        await self.wait_until_ready()
        if (
            not hasattr(self, "services")
            or not self.services
            or not self.services.config
        ):
            logger.debug("Config service unavailable; skipping role refresh")
            return

        guild = self.get_guild(guild_id)
        if not guild:
            logger.debug("Guild %s not found for role refresh", guild_id)
            return

        role_keys = [
            "roles.bot_verified_role",
            "roles.main_role",
            "roles.affiliate_role",
            "roles.nonmember_role",
        ]

        expected_ids: set[str] = set()
        for key in role_keys:
            ids = await self.services.config.get_guild_setting(guild_id, key, [])
            if isinstance(ids, list) and ids:
                role_id = str(ids[0])
                if role_id:
                    expected_ids.add(role_id)

        previous_ids = self._guild_role_expectations.get(guild_id, set())
        removed_ids = previous_ids - expected_ids
        for stale_id in removed_ids:
            self.role_cache.pop(stale_id, None)

        for role_id in expected_ids:
            role = guild.get_role(int(role_id))
            if role:
                self.role_cache[role_id] = role
            else:
                await self._warn_missing_role(guild, role_id)

        self._guild_role_expectations[guild_id] = expected_ids
        logger.info(
            "Refreshed %s role mappings for guild %s (%s)",
            len(expected_ids),
            guild.name,
            source or "manual",
        )

    async def role_refresh_task(self) -> None:
        """Background task that periodically refreshes guild role caches."""
        await self.wait_until_ready()
        interval_seconds = 300  # 5 minutes

        while not self.is_closed():
            try:
                if (
                    not hasattr(self, "services")
                    or not self.services
                    or not self.services.config
                ):
                    await asyncio.sleep(interval_seconds)
                    continue

                for guild in list(self.guilds):
                    refreshed = await self.services.config.maybe_refresh_guild(
                        guild.id
                    )
                    if refreshed:
                        await self.refresh_guild_roles(guild.id, source="scheduled")
            except asyncio.CancelledError:
                logger.info("Role refresh task cancelled")
                break
            except Exception as exc:
                logger.exception("Error during scheduled role refresh", exc_info=exc)

            await asyncio.sleep(interval_seconds)

    async def _warn_missing_role(
        self, guild: discord.Guild, role_id: str
    ) -> None:
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
                f"Role {role_id} missing in '{guild.name}' (already reported)."
            )

    async def token_cleanup_task(self) -> None:
        """
        Periodically cleans up expired tokens.
        """
        while not self.is_closed():
            await asyncio.sleep(300)  # Run every 5 minutes
            cleanup_tokens()
            logger.debug("Expired tokens cleaned up.")

    async def attempts_cleanup_task(self) -> None:
        """
        Periodically cleans up expired rate-limiting data.
        """
        while not self.is_closed():
            await asyncio.sleep(300)  # Run every 5 minutes
            # Cleanup_attempts is an async coroutine; await it to avoid "coroutine was never awaited" warnings
            await cleanup_attempts()

    async def log_cleanup_task(self) -> None:
        """
        Daily cleanup of old logs based on retention policies.

        Runs at the configured cleanup_hour_utc time each day.
        """
        await self.wait_until_ready()

        # Get cleanup hour from config (default to 3 AM UTC)
        cleanup_hour_utc = config.get("log_retention", {}).get("cleanup_hour_utc", 3)

        while not self.is_closed():
            try:
                # Calculate seconds until next cleanup time
                from datetime import UTC, datetime, timedelta

                now = datetime.now(UTC)
                target_time = now.replace(
                    hour=cleanup_hour_utc, minute=0, second=0, microsecond=0
                )

                # If target time has passed today, schedule for tomorrow
                if now >= target_time:
                    target_time += timedelta(days=1)

                seconds_until_cleanup = (target_time - now).total_seconds()

                logger.info(
                    f"Log cleanup scheduled for {target_time.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                    f"({seconds_until_cleanup / 3600:.1f} hours from now)"
                )

                # Wait until cleanup time
                await asyncio.sleep(seconds_until_cleanup)

                # Run cleanup
                logger.info("Starting scheduled log cleanup")
                cleanup_service = LogCleanupService(config)
                summary = await cleanup_service.cleanup_all()

                logger.info(
                    f"Log cleanup completed: {summary}",
                    extra={"cleanup_summary": summary},
                )

            except asyncio.CancelledError:
                logger.info("Log cleanup task cancelled")
                break
            except Exception as e:
                logger.exception("Error in log cleanup task", exc_info=e)
                # Wait 1 hour before retrying on error
                await asyncio.sleep(3600)

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
        if hasattr(self, "internal_api") and self.internal_api:
            try:
                await self.internal_api.stop()
                logger.info("Internal API server stopped")
            except Exception as e:
                logger.exception("Error stopping internal API server", exc_info=e)

        # Cleanup services
        if hasattr(self, "services") and self.services:
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
