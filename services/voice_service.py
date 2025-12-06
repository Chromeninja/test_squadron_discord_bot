"""
Voice service for managing voice channels and related functionality.
"""

import asyncio
import time
from collections.abc import Coroutine, Iterable
from typing import TYPE_CHECKING, Any, Optional, cast

import discord

from helpers.discord_api import delete_channel
from helpers.voice_permissions import enforce_permission_changes
from services.db.database import Database
from utils.types import VoiceChannelInfo, VoiceChannelResult

from .base import BaseService
from .config_service import ConfigService

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot


# Function alias for test patching - avoids circular import
def update_last_used_jtc_channel(guild_id: int, user_id: int, jtc_channel_id: int):
    """Alias for test patching to avoid circular imports."""
    from helpers.voice_settings import update_last_used_jtc_channel as real_func

    return real_func(guild_id, user_id, jtc_channel_id)


class VoiceService(BaseService):
    """
    Service for managing voice channels in a race-safe, predictable manner.

    Handles voice channel creation, deletion, cooldowns, and settings
    with proper async safety and deduplication.
    """

    ORPHAN_OWNER_ID = 0

    def __init__(
        self,
        config_service: ConfigService,
        bot: Optional["discord.Client"] = None,
        test_mode: bool = False,
    ) -> None:
        super().__init__("voice")
        self.config_service = config_service
        self.bot = bot  # Store bot instance for channel operations
        self.test_mode = test_mode
        self._background_tasks: set[asyncio.Task] = set()
        # Track creation locks (tagged keys) and when they were last used for cleanup
        # Keys are prefixed tuples so user-scoped locks cannot collide with JTC locks
        self._creation_locks: dict[tuple[str, int, int], asyncio.Lock] = {}
        self._lock_last_used: dict[tuple[str, int, int], float] = {}
        self._locks_lock = asyncio.Lock()
        self._creation_unmark_delay = 2.0  # seconds to keep users marked as creating

        # Track managed voice channels like the old code
        self.managed_voice_channels: set[int] = set()

        # Track users currently in the process of creating a channel
        # Keyed by (guild_id, user_id) so hopping between different JTC entry channels
        # cannot trigger parallel creations for the same user
        self._users_creating_channels: set[tuple[int, int]] = set()

        # Debug logging configuration - defaults to False for production
        self.debug_logging_enabled = False

        # In-memory cache of voice channel members (channel_id -> set of user_ids)
        # This is populated from Gateway events and has no Discord API overhead
        self._voice_channel_members: dict[int, set[int]] = {}
        self._voice_channels_has_previous_owner = False

    def _spawn_background_task(
        self, coro: Coroutine[Any, Any, Any], *, name: str
    ) -> asyncio.Task:
        """Create and track a background task with exception logging."""

        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)

        def _discard_and_log(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            try:
                exc = t.exception()
                if exc:
                    self.logger.exception(
                        "Background task %s failed", name, exc_info=exc
                    )
            except asyncio.CancelledError:
                self.logger.debug("Background task %s cancelled", name)
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.warning(
                    "Failed to inspect background task %s: %s", name, exc
                )

        task.add_done_callback(_discard_and_log)
        return task

    async def _initialize_impl(self) -> None:
        """Initialize voice service."""
        await self._ensure_voice_tables()

        # Load debug logging configuration
        self.debug_logging_enabled = await self.config_service.get_global_setting(
            "voice_debug_logging_enabled", False
        )

        # Production safety warning
        if self.debug_logging_enabled:
            self.logger.warning(
                "Voice debug logging is ENABLED - this may log PII and generate high volume. "
                "Ensure this is intentional and disable in production."
            )

        # Load existing managed channels
        await self._load_managed_channels()

        # Clean up orphaned JTC data (defense-in-depth)
        await self._cleanup_orphaned_jtc_data()

        if not self.test_mode:
            self._spawn_background_task(self._cleanup_task(), name="voice.cleanup_task")
            self._spawn_background_task(
                self._run_reconcile_after_ready(),
                name="voice.reconcile_after_ready",
            )

    async def _shutdown_impl(self) -> None:
        """Cleanup resources during service shutdown."""
        # Log any users still marked as creating
        if self._users_creating_channels:
            self.logger.warning(
                f"Shutting down with {len(self._users_creating_channels)} users still marked as creating channels"
            )
            self._users_creating_channels.clear()
        # Cancel and await all background tasks
        for task in list(self._background_tasks):
            task.cancel()
        for task in list(self._background_tasks):
            try:
                await task
            except asyncio.CancelledError:
                continue
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.warning(
                    "Background task %s raised during shutdown: %s",
                    task.get_name(),
                    exc,
                )
        self._background_tasks.clear()

    async def _load_managed_channels(self) -> None:
        """Load existing managed channels from database. Do not delete DB rows if channel is not in cache; defer to reconciliation."""
        try:
            # Get startup cleanup mode setting
            startup_cleanup_mode = await self.config_service.get_global_setting(
                "voice.startup_cleanup_mode", "delayed"
            )

            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT voice_channel_id FROM voice_channels WHERE is_active = 1"
                )
                rows = await cursor.fetchall()

                loaded_count = 0
                deferred_count = 0
                empty_immediate_count = 0

                for (channel_id,) in rows:
                    channel = self.bot.get_channel(channel_id) if self.bot else None
                    if channel is not None:
                        voice_like: (
                            discord.VoiceChannel | discord.StageChannel | None
                        ) = None
                        if isinstance(
                            channel, (discord.VoiceChannel, discord.StageChannel)
                        ):
                            voice_like = channel
                        elif hasattr(channel, "members") and hasattr(channel, "delete"):
                            voice_like = cast("discord.VoiceChannel", channel)

                        if voice_like:
                            if (
                                len(voice_like.members) == 0
                                and startup_cleanup_mode == "immediate"
                            ):
                                # Empty channel with immediate cleanup mode - clean up now
                                self.logger.info(
                                    f"startup: immediately cleaning empty channel {channel_id} per startup_cleanup_mode"
                                )
                                try:
                                    await self._cleanup_empty_channel(channel_id)
                                    empty_immediate_count += 1
                                except Exception as e:
                                    self.logger.exception(
                                        f"Error immediately cleaning up channel {channel_id}",
                                        exc_info=e,
                                    )
                            else:
                                # Channel has members or delayed mode - add to managed set
                                self.managed_voice_channels.add(channel_id)
                                loaded_count += 1
                        else:
                            # Not a VoiceChannel, skip
                            deferred_count += 1
                            self.logger.debug(
                                f"startup: channel {channel_id} not a VoiceChannel, deferring to reconcile"
                            )
                    else:
                        deferred_count += 1
                        self.logger.debug(
                            f"startup: channel {channel_id} not in cache yet, deferring to reconcile"
                        )

                log_msg = f"Loaded {loaded_count} managed voice channels for later reconciliation; {deferred_count} deferred due to not in cache"
                if empty_immediate_count > 0:
                    log_msg += f"; {empty_immediate_count} empty channels immediately cleaned per startup_cleanup_mode"
                self.logger.info(log_msg)

        except Exception as e:
            self.logger.exception("Error loading managed channels", exc_info=e)

    async def _cleanup_orphaned_jtc_data(self) -> None:
        """
        Clean up database rows scoped to JTC IDs that are not in current guild configs.
        This is a defense-in-depth measure for startup reconciliation.
        """
        try:
            if not self.bot:
                self.logger.warning("Bot not available for orphaned JTC cleanup")
                return

            if not hasattr(self.bot, "guilds") or not isinstance(
                self.bot.guilds, Iterable
            ):
                self.logger.warning(
                    "Bot guilds collection missing or not iterable; skipping orphaned JTC cleanup"
                )
                return

            total_guilds_processed = 0
            total_rows_cleaned = 0

            # Process each guild the bot is in
            for guild in self.bot.guilds:
                guild_id = guild.id

                try:
                    # Get currently configured JTC channel IDs for this guild
                    valid_jtc_ids = await self.config_service.get_guild_jtc_channels(
                        guild_id
                    )

                    # Clean up orphaned data
                    deleted_counts = await Database.cleanup_orphaned_jtc_data(
                        guild_id, set(valid_jtc_ids)
                    )

                    guild_total = sum(deleted_counts.values())
                    if guild_total > 0:
                        self.logger.info(
                            f"Cleaned orphaned JTC data for guild {guild.name} ({guild_id}): {guild_total} rows across tables"
                        )
                        total_rows_cleaned += guild_total

                    total_guilds_processed += 1

                except Exception as e:
                    self.logger.exception(
                        f"Error cleaning orphaned JTC data for guild {guild_id}",
                        exc_info=e,
                    )

            if total_rows_cleaned > 0:
                self.logger.info(
                    f"Orphaned JTC cleanup complete: processed {total_guilds_processed} guilds, cleaned {total_rows_cleaned} total rows"
                )
            else:
                self.logger.info(
                    f"Orphaned JTC cleanup complete: processed {total_guilds_processed} guilds, no orphaned data found"
                )

        except Exception as e:
            self.logger.exception("Error during orphaned JTC cleanup", exc_info=e)

    async def _ensure_voice_tables(self) -> None:
        """Ensure voice-related database tables exist."""
        async with Database.get_connection() as db:
            # Enhanced voice channels table - supports multiple channels per owner per JTC
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    jtc_channel_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    voice_channel_id INTEGER NOT NULL UNIQUE,
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    last_activity INTEGER DEFAULT (strftime('%s','now')),
                    is_active INTEGER DEFAULT 1,
                    previous_owner_id INTEGER
                )
            """
            )

            # Ensure previous_owner_id column exists for older databases
            cursor = await db.execute("PRAGMA table_info(voice_channels)")
            column_names = [col[1] for col in await cursor.fetchall()]
            if "previous_owner_id" not in column_names:
                await db.execute(
                    "ALTER TABLE voice_channels ADD COLUMN previous_owner_id INTEGER"
                )
            self._voice_channels_has_previous_owner = True

            # Create indexes for efficient queries
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_voice_channels_guild_owner_active
                ON voice_channels(guild_id, owner_id, is_active)
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_voice_channels_guild_jtc_active
                ON voice_channels(guild_id, jtc_channel_id, is_active)
            """
            )

            # Voice channel settings - now references voice channels by voice_channel_id
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_channel_settings (
                    guild_id INTEGER NOT NULL,
                    jtc_channel_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    voice_channel_id INTEGER NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT,
                    PRIMARY KEY (guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key),
                    FOREIGN KEY (voice_channel_id)
                    REFERENCES voice_channels(voice_channel_id)
                    ON DELETE CASCADE
                )
            """
            )

            # Voice cooldowns (per user per JTC channel)
            # Check if table exists with correct schema
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='voice_cooldowns'"
            )
            table_exists = await cursor.fetchone() is not None

            if table_exists:
                # Check if it has the correct column name
                cursor = await db.execute("PRAGMA table_info(voice_cooldowns)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                # If it has 'last_creation' instead of 'timestamp', recreate the table
                if "last_creation" in column_names and "timestamp" not in column_names:
                    self.logger.info(
                        "Migrating voice_cooldowns table to use 'timestamp' column"
                    )
                    await db.execute("DROP TABLE voice_cooldowns")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_cooldowns (
                    guild_id INTEGER NOT NULL,
                    jtc_channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
                )
            """
            )

            await db.commit()

    def _mark_user_creating(self, guild_id: int, user_id: int) -> None:
        """Mark a user as currently creating a channel (guild-scoped)."""
        key = (guild_id, user_id)
        already_marked = key in self._users_creating_channels
        self._users_creating_channels.add(key)
        if self.debug_logging_enabled:
            self.logger.debug(
                "MARK: mark_creating guild=%s user=%s already_marked=%s",
                guild_id,
                user_id,
                already_marked,
            )

    def _unmark_user_creating(self, guild_id: int, user_id: int) -> None:
        """Unmark a user as creating a channel across the entire guild."""
        key = (guild_id, user_id)
        existed = key in self._users_creating_channels
        self._users_creating_channels.discard(key)
        if self.debug_logging_enabled:
            self.logger.debug(
                "MARK: unmark_creating guild=%s user=%s existed=%s",
                guild_id,
                user_id,
                existed,
            )

    def _is_user_creating(self, guild_id: int, user_id: int) -> bool:
        """Check if a user is currently creating a channel anywhere in the guild."""
        key = (guild_id, user_id)
        return key in self._users_creating_channels

    async def _delayed_unmark_user_creating(
        self,
        guild_id: int,
        user_id: int,
        delay: float | None = None,
    ) -> None:
        """Unmark a user after an optional delay to absorb duplicate events."""
        if delay and delay > 0:
            await asyncio.sleep(delay)
        self._unmark_user_creating(guild_id, user_id)

    async def _get_creation_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        """Get or create a per-user lock for voice channel creation.

        All channel creation must use per-user locks to prevent race conditions.
        This prevents the same user from creating multiple channels concurrently,
        even across different JTC entry points.

        TODO: Consider adding asyncio.wait_for(lock.acquire(), timeout=5.0) if
        deadlocks are observed in production. Current implementation trusts the
        lock will be released promptly by scheduled unmark tasks.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            asyncio.Lock for this specific user in this guild
        """
        key = ("user", guild_id, user_id)

        async with self._locks_lock:
            if key not in self._creation_locks:
                self._creation_locks[key] = asyncio.Lock()
            self._lock_last_used[key] = time.time()
            if self.debug_logging_enabled:
                self.logger.debug(
                    "LOCK: get_creation_lock guild=%s user=%s key=%r",
                    guild_id,
                    user_id,
                    key,
                )
            return self._creation_locks[key]

    async def _cleanup_stale_locks(self, max_age_seconds: int = 300) -> None:
        """Remove lock objects that have not been used recently."""
        cutoff = time.time() - max_age_seconds
        async with self._locks_lock:
            for key in list(self._lock_last_used.keys()):
                last_used = self._lock_last_used.get(key, 0)
                if last_used >= cutoff:
                    continue
                lock = self._creation_locks.get(key)
                if lock and lock.locked():
                    continue
                self._creation_locks.pop(key, None)
                self._lock_last_used.pop(key, None)

    def _get_voice_channel_member_count(
        self,
        channel_or_id: discord.VoiceChannel | discord.StageChannel | int | None,
    ) -> int:
        """Return the member count for a voice-like channel using cache fallback."""

        if channel_or_id is None:
            return 0

        channel: discord.VoiceChannel | discord.StageChannel | None
        channel_id: int | None

        if isinstance(channel_or_id, int):
            channel_id = channel_or_id
            channel_candidate = self.bot.get_channel(channel_id) if self.bot else None
            if isinstance(
                channel_candidate, (discord.VoiceChannel, discord.StageChannel)
            ):
                channel = channel_candidate
            else:
                channel = None
        else:
            channel = channel_or_id
            channel_id = getattr(channel, "id", None)

        try:
            if channel and hasattr(channel, "members"):
                return len(channel.members)  # type: ignore[arg-type]
        except Exception:
            pass

        if channel_id is not None:
            cached = self._voice_channel_members.get(channel_id)
            if cached is not None:
                return len(cached)

        return 0

    async def can_create_voice_channel(
        self,
        guild_id: int,
        jtc_channel_id: int,
        user_id: int,
        *,
        bypass_cooldown: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Check if a user can create a voice channel.

        For multi-channel support, we only check time-based cooldown,
        not whether the user already has an existing channel.

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            user_id: Discord user ID

        Returns:
            Tuple of (can_create, error_code_if_not) - returns error code, not formatted message
        """
        self._ensure_initialized()

        # Check if user is already in the process of creating a channel
        if self._is_user_creating(guild_id, user_id):
            self.logger.debug(
                f"User {user_id} is already creating a channel in guild {guild_id}"
            )
            return False, "CREATING"

        # Only check time-based cooldown (removed existing channel check for multi-channel support)
        if not bypass_cooldown:
            cooldown_seconds = await self.config_service.get_guild_setting(
                guild_id, "voice.cooldown_seconds", 5
            )

            if await self._is_on_cooldown(
                guild_id, jtc_channel_id, user_id, cooldown_seconds
            ):
                # Return error code with seconds embedded (will be extracted at command layer)
                return (
                    False,
                    f"COOLDOWN:{cooldown_seconds}",
                )

        return True, None

    async def delete_voice_channel(
        self, guild_id: int, voice_channel_id: int, reason: str = "Channel cleanup"
    ) -> bool:
        """
        Delete a voice channel and clean up database records.

        Args:
            guild_id: Discord guild ID
            voice_channel_id: Voice channel ID to delete
            reason: Reason for deletion

        Returns:
            True if deletion was successful
        """
        self._ensure_initialized()

        try:
            # Find channel record
            async with Database.get_connection() as db:
                async with db.execute(
                    """
                    SELECT guild_id, jtc_channel_id, owner_id
                    FROM voice_channels
                    WHERE voice_channel_id = ? AND guild_id = ?
                """,
                    (voice_channel_id, guild_id),
                ) as cursor:
                    row = await cursor.fetchone()

                if not row:
                    self.logger.debug(
                        f"Voice channel {voice_channel_id} not found in database"
                    )
                    return False

                guild_id, _jtc_channel_id, _owner_id = row

                # Delete from Discord
                channel = self.bot.get_channel(voice_channel_id) if self.bot else None
                # Only delete if channel is a GuildChannel and not PrivateChannel/Thread
                if channel and isinstance(channel, discord.VoiceChannel):
                    result = await delete_channel(channel)
                    success = bool(result)
                else:
                    self.logger.warning(
                        f"Channel {voice_channel_id} is not a VoiceChannel or does not exist; skipping Discord deletion."
                    )
                    success = False

                # Clean up database records
                await self.cleanup_by_channel_id(voice_channel_id)

                self.logger.info(f"Deleted voice channel {voice_channel_id}: {reason}")
                return success

        except Exception as e:
            self.logger.exception(
                f"Failed to delete voice channel {voice_channel_id}: {e}"
            )
            return False

    async def handle_channel_deleted(self, guild_id: int, channel_id: int) -> None:
        """
        Handle when a voice channel is deleted externally (e.g., by Discord or manual deletion).

        Detects if deleted channel is a JTC channel and removes from config.
        Also cleans up any managed channels and database records.

        Args:
            guild_id: The guild ID where the channel was deleted
            channel_id: The ID of the deleted channel
        """
        self._ensure_initialized()

        try:
            # Check if this is a JTC channel
            is_jtc = await self._is_join_to_create_channel(guild_id, channel_id)

            if is_jtc:
                # This is a JTC channel deletion - remove from config and cleanup
                self.logger.info(
                    f"JTC channel {channel_id} deleted in guild {guild_id}, "
                    f"removing from config and cleaning up associated data"
                )

                cleanup_result = await self.remove_jtc_channel_from_config(
                    guild_id, channel_id, cleanup_managed=True
                )

                if not cleanup_result["success"]:
                    self.logger.warning(
                        f"Error removing JTC channel {channel_id} from config: "
                        f"{cleanup_result['error']}"
                    )
                else:
                    self.logger.info(
                        f"JTC channel {channel_id} removal complete: "
                        f"managed_cleanup={cleanup_result['managed_cleanup']}, "
                        f"db_purge={cleanup_result['db_purge']}"
                    )

            elif await self._is_managed_channel(channel_id):
                # This is a managed voice channel - clean up database records
                self.logger.info(
                    f"Cleaning up records for deleted managed channel {channel_id}"
                )
                await self._cleanup_empty_channel(channel_id)
            else:
                # Not a managed channel - log for reference
                self.logger.debug(
                    f"Channel {channel_id} was not a managed voice channel"
                )

        except Exception as e:
            self.logger.exception(
                f"Error handling channel deletion for {channel_id}", exc_info=e
            )

    async def get_user_voice_channel(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> int | None:
        """
        Get the voice channel ID for a user in a specific JTC channel.

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            user_id: Discord user ID

        Returns:
            Voice channel ID or None if not found
        """
        async with (
            Database.get_connection() as db,
            db.execute(
                """
                SELECT voice_channel_id FROM voice_channels
                WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (guild_id, jtc_channel_id, user_id),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            return row[0] if row else None

    async def _get_any_user_voice_channel(
        self, guild_id: int, user_id: int
    ) -> int | None:
        """
        Get ANY existing voice channel ID for a user in a guild, regardless of which JTC created it.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Voice channel ID or None if not found
        """
        async with (
            Database.get_connection() as db,
            db.execute(
                """
                SELECT voice_channel_id FROM voice_channels
                WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (guild_id, user_id),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            return row[0] if row else None

    async def cleanup_stale_channels(self, guild: discord.Guild) -> int:
        """
        Clean up stale voice channels that no longer exist on Discord.

        Args:
            guild: Discord guild to clean up

        Returns:
            Number of channels cleaned up
        """
        self._ensure_initialized()

        cleaned_count = 0

        # Get all voice channels for this guild from database
        async with (
            Database.get_connection() as db,
            db.execute(
                """
                SELECT voice_channel_id, jtc_channel_id, owner_id
                FROM voice_channels
                WHERE guild_id = ? AND is_active = 1
            """,
                (guild.id,),
            ) as cursor,
        ):
            voice_channels = await cursor.fetchall()

        for voice_channel_id, _jtc_channel_id, _owner_id in voice_channels:
            # Check if channel still exists on Discord
            channel = guild.get_channel(voice_channel_id)
            if not channel:
                # Channel no longer exists, clean up database
                await self.cleanup_by_channel_id(voice_channel_id)
                cleaned_count += 1
                self.logger.debug(
                    f"Cleaned up stale voice channel record: {voice_channel_id}"
                )

        if cleaned_count > 0:
            self.logger.info(
                f"Cleaned up {cleaned_count} stale voice channels in {guild.name}"
            )

        return cleaned_count

    async def _is_on_cooldown(
        self, guild_id: int, jtc_channel_id: int, user_id: int, cooldown_seconds: int
    ) -> bool:
        """Check if a user is on cooldown for voice channel creation."""
        async with (
            Database.get_connection() as db,
            db.execute(
                """
                SELECT timestamp FROM voice_cooldowns
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
                (guild_id, jtc_channel_id, user_id),
            ) as cursor,
        ):
            row = await cursor.fetchone()

        if not row:
            return False

        last_creation = row[0]
        current_time = int(time.time())
        return (current_time - last_creation) < cooldown_seconds

    async def _update_cooldown(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> None:
        """Update the cooldown timestamp for a user."""
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO voice_cooldowns
                (guild_id, jtc_channel_id, user_id, timestamp)
                VALUES (?, ?, ?, ?)
            """,
                (guild_id, jtc_channel_id, user_id, int(time.time())),
            )
            await db.commit()

    async def _store_voice_channel(
        self, guild_id: int, jtc_channel_id: int, owner_id: int, voice_channel_id: int
    ) -> None:
        """Store voice channel record in database."""
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id)
                VALUES (?, ?, ?, ?)
            """,
                (guild_id, jtc_channel_id, owner_id, voice_channel_id),
            )
            await db.commit()

    async def cleanup_by_channel_id(self, voice_channel_id: int) -> None:
        """Clean up database records for a specific voice channel."""
        async with Database.get_connection() as db:
            # Clean up settings for this specific channel
            await db.execute(
                """
                DELETE FROM voice_channel_settings
                WHERE voice_channel_id = ?
            """,
                (voice_channel_id,),
            )

            # Remove voice channel record entirely to avoid stale rows
            await db.execute(
                """
                DELETE FROM voice_channels
                WHERE voice_channel_id = ?
            """,
                (voice_channel_id,),
            )

            await db.commit()

    async def _purge_inactive_voice_channels(
        self, older_than_seconds: int | None = None
    ) -> int:
        """Delete inactive voice channel rows to keep the table lean."""
        query = "DELETE FROM voice_channels WHERE is_active = 0"
        params: tuple[int, ...] = ()
        if older_than_seconds is not None:
            cutoff = int(time.time()) - older_than_seconds
            query += " AND last_activity < ?"
            params = (cutoff,)

        async with Database.get_connection() as db:
            cursor = await db.execute(query, params)
            deleted = cursor.rowcount if cursor.rowcount not in (None, -1) else 0
            await db.commit()
        return deleted

    async def _generate_channel_name(self, user: discord.Member) -> str:
        """Generate a name for a voice channel."""
        # Try to get game activity
        for activity in user.activities:
            if isinstance(activity, discord.Game):
                return f"{user.display_name}'s {activity.name}"

        # Fall back to default name
        return f"{user.display_name}'s Channel"

    async def _cleanup_task(self) -> None:
        """Background task to clean up expired data."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                # Clean up old cooldown records (older than 24 hours)
                cutoff_time = int(time.time()) - (24 * 3600)
                async with Database.get_connection() as db:
                    await db.execute(
                        """
                        DELETE FROM voice_cooldowns
                        WHERE timestamp < ?
                    """,
                        (cutoff_time,),
                    )
                    await db.commit()

                self.logger.debug("Cleaned up old voice cooldown records")

                deleted_rows = await self._purge_inactive_voice_channels(
                    older_than_seconds=7 * 24 * 3600
                )
                if deleted_rows:
                    self.logger.debug(
                        f"Purged {deleted_rows} inactive voice channel records"
                    )

                await self._cleanup_stale_locks()

            except Exception as e:
                self.logger.exception("Error in voice cleanup task", exc_info=e)

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the voice service."""
        base_health = await super().health_check()

        try:
            async with Database.get_connection() as db:
                # Count active voice channels
                async with db.execute(
                    """
                    SELECT COUNT(*) FROM voice_channels WHERE is_active = 1
                """
                ) as cursor:
                    row = await cursor.fetchone()
                    active_channels = row[0] if row is not None else 0

                # Count total cooldown records
                async with db.execute(
                    """
                    SELECT COUNT(*) FROM voice_cooldowns
                """
                ) as cursor:
                    row = await cursor.fetchone()
                    cooldown_records = row[0] if row is not None else 0
        except Exception:
            active_channels = "error"
            cooldown_records = "error"

        return {
            **base_health,
            "active_voice_channels": active_channels,
            "cooldown_records": cooldown_records,
            "creation_locks": len(self._creation_locks),
        }

    async def get_voice_settings_snapshot(
        self,
        guild_id: int,
        jtc_channel_id: int,
        owner_id: int,
        voice_channel_id: int | None = None,
        guild: discord.Guild | None = None,
    ) -> "VoiceSettingsSnapshot | None":
        """
        Get a complete snapshot of voice channel settings.

        This is the unified method for retrieving voice settings used by:
        - Discord commands (/voice list, /voice admin_list)
        - Backend API endpoints (/api/voice/search, /api/voice/active, /api/voice/user-settings)

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            owner_id: Channel owner user ID
            voice_channel_id: Optional voice channel ID if currently active
            guild: Optional Discord guild object for name resolution

        Returns:
            VoiceSettingsSnapshot or None if no settings found
        """
        from utils.types import (
            PermissionOverride,
            PrioritySpeakerSetting,
            PTTSetting,
            SoundboardSetting,
            VoiceSettingsSnapshot,
        )

        try:
            async with Database.get_connection() as db:
                # Get basic channel settings
                cursor = await db.execute(
                    """
                    SELECT channel_name, user_limit, lock
                    FROM channel_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                row = await cursor.fetchone()

                if not row:
                    # No settings found
                    return None

                channel_name, user_limit, lock = row

                # Get channel metadata if voice_channel_id provided
                created_at = None
                last_activity = None
                is_active = False

                if voice_channel_id:
                    cursor = await db.execute(
                        """
                        SELECT created_at, last_activity, is_active
                        FROM voice_channels
                        WHERE voice_channel_id = ? AND owner_id = ?
                    """,
                        (voice_channel_id, owner_id),
                    )
                    vc_row = await cursor.fetchone()
                    if vc_row:
                        created_at, last_activity, is_active = vc_row
                        is_active = bool(is_active)

                # Get permissions
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, permission
                    FROM channel_permissions
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                perm_rows = await cursor.fetchall()

                # Get PTT settings
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, ptt_enabled
                    FROM channel_ptt_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                ptt_rows = await cursor.fetchall()

                # Get priority speaker settings
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, priority_enabled
                    FROM channel_priority_speaker_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                priority_rows = await cursor.fetchall()

                # Get soundboard settings
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, soundboard_enabled
                    FROM channel_soundboard_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                soundboard_rows = await cursor.fetchall()

                # Build snapshot with unresolved names (resolution happens separately)
                permissions = [
                    PermissionOverride(
                        target_id=str(target_id),
                        target_type=target_type,
                        permission=permission,
                    )
                    for target_id, target_type, permission in perm_rows
                ]

                ptt_settings = [
                    PTTSetting(
                        target_id=str(target_id),
                        target_type=target_type,
                        ptt_enabled=bool(ptt_enabled),
                    )
                    for target_id, target_type, ptt_enabled in ptt_rows
                ]

                priority_settings = [
                    PrioritySpeakerSetting(
                        target_id=str(target_id),
                        target_type=target_type,
                        priority_enabled=bool(priority_enabled),
                    )
                    for target_id, target_type, priority_enabled in priority_rows
                ]

                soundboard_settings = [
                    SoundboardSetting(
                        target_id=str(target_id),
                        target_type=target_type,
                        soundboard_enabled=bool(soundboard_enabled),
                    )
                    for target_id, target_type, soundboard_enabled in soundboard_rows
                ]

                snapshot = VoiceSettingsSnapshot(
                    guild_id=guild_id,
                    jtc_channel_id=jtc_channel_id,
                    owner_id=owner_id,
                    voice_channel_id=voice_channel_id,
                    channel_name=channel_name,
                    user_limit=user_limit,
                    is_locked=bool(lock),
                    created_at=created_at,
                    last_activity=last_activity,
                    is_active=is_active,
                    permissions=permissions,
                    ptt_settings=ptt_settings,
                    priority_speaker_settings=priority_settings,
                    soundboard_settings=soundboard_settings,
                )

                # Resolve names if guild provided
                if guild:
                    from helpers.voice_settings import resolve_target_names

                    await resolve_target_names(guild, snapshot)

                return snapshot

        except Exception as e:
            self.logger.exception("Error getting voice settings snapshot", exc_info=e)
            return None

    # Additional methods for cog integration

    async def create_user_voice_channel(
        self, guild_id: int, user_id: int, user: discord.Member
    ) -> VoiceChannelResult:
        """
        Create a voice channel for a user with result handling.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            user: Discord member object

        Returns:
            VoiceChannelResult with success status and error code (not formatted message)
        """
        try:
            guild = user.guild
            if not guild:
                return VoiceChannelResult(False, error="UNKNOWN")

            # Find a suitable JTC channel (simplified for now)
            jtc_channels = await self._get_guild_jtc_channels(guild_id)
            if not jtc_channels:
                return VoiceChannelResult(False, error="NO_JTC_CONFIGURED")

            # Use first available JTC channel
            jtc_channel_id = jtc_channels[0]
            jtc_channel = guild.get_channel(jtc_channel_id)

            if not jtc_channel or not isinstance(jtc_channel, discord.VoiceChannel):
                return VoiceChannelResult(False, error="JTC_NOT_FOUND")

            # Check if user can create
            can_create, reason = await self.can_create_voice_channel(
                guild_id, jtc_channel_id, user_id
            )

            if not can_create:
                # The reason is already an error code from can_create_voice_channel
                return VoiceChannelResult(False, error=reason)

            # Create the channel using the authoritative path
            channel = await self._create_user_channel(guild, jtc_channel, user)

            if channel:
                return VoiceChannelResult(
                    True, channel_id=channel.id, channel_mention=channel.mention
                )

            return VoiceChannelResult(False, error="CREATION_FAILED")

        except Exception as e:
            self.logger.exception("Error creating user voice channel", exc_info=e)
            return VoiceChannelResult(False, error="UNKNOWN")

    async def get_user_voice_channel_info(
        self, guild_id: int, user_id: int
    ) -> VoiceChannelInfo | None:
        """
        Get a user's active voice channel info.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            VoiceChannelInfo if found, None otherwise
        """
        try:
            async with (
                Database.get_connection() as db,
                db.execute(
                    """
                    SELECT guild_id, jtc_channel_id, voice_channel_id, owner_id,
                           created_at, last_activity, is_active
                    FROM voice_channels
                    WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                    LIMIT 1
                """,
                    (guild_id, user_id),
                ) as cursor,
            ):
                row = await cursor.fetchone()

                if row:
                    return VoiceChannelInfo(
                        guild_id=row[0],
                        jtc_channel_id=row[1],
                        channel_id=row[2],
                        owner_id=row[3],
                        created_at=row[4],
                        last_activity=row[5],
                        is_active=bool(row[6]),
                    )
                return None

        except Exception as e:
            self.logger.exception("Error getting user voice channel", exc_info=e)
            return None

    async def create_settings_embed(self, guild_id: int, user_id: int) -> discord.Embed:
        """
        Create an embed showing voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Discord embed with settings information
        """
        embed = discord.Embed(
            title="🔧 Voice Channel Settings",
            description="Manage your voice channel settings below.",
            color=0x7289DA,
        )

        # Add current settings (placeholder implementation)
        embed.add_field(
            name="Current Settings", value="Settings would be loaded here", inline=False
        )

        return embed

    async def create_settings_view(
        self, guild_id: int, user_id: int
    ) -> discord.ui.View:
        """
        Create a view for voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Discord UI view with settings controls
        """
        # This would return an actual settings view
        # For now, return a basic view
        return discord.ui.View()

    async def get_admin_role_ids(self, guild_id: int) -> list[int]:
        """Get privileged role IDs (admins + moderators) for a specific guild.

        Args:
            guild_id: The Discord guild ID to get admin roles for

        Returns:
            List of role IDs that have admin or moderator permissions
        """
        try:
            bot_admin_roles = await self.config_service.get_guild_setting(
                guild_id=guild_id,
                key="roles.bot_admins",
                default=[],
            )
            moderator_roles = await self.config_service.get_guild_setting(
                guild_id=guild_id,
                key="roles.moderators",
                default=[],
            )
            return (bot_admin_roles or []) + (moderator_roles or [])
        except Exception as e:
            self.logger.exception(
                f"Error getting admin role IDs for guild {guild_id}", exc_info=e
            )
            return []

    def get_voice_channel_members(self, channel_id: int) -> list[int]:
        """
        Get list of user IDs currently in a voice channel.

        This data comes from the Gateway cache (no Discord API calls).
        Returns empty list if channel has no members or is not cached.

        Args:
            channel_id: Discord voice channel ID

        Returns:
            List of user IDs currently in the channel
        """
        return list(self._voice_channel_members.get(channel_id, set()))

    async def handle_voice_state_change(
        self,
        member: discord.Member,
        before_channel: discord.VoiceChannel | None,
        after_channel: discord.VoiceChannel | None,
    ) -> None:
        """
        Handle voice state changes for join-to-create functionality.

        Args:
            member: Discord member
            before_channel: Channel member left (if any)
            after_channel: Channel member joined (if any)
        """
        guild = member.guild
        guild_id = guild.id

        if self.debug_logging_enabled:
            self.logger.info(
                "VS: event guild=%s member=%s before_channel=%s after_channel=%s",
                guild_id,
                getattr(member, "id", None),
                before_channel.id if before_channel else None,
                after_channel.id if after_channel else None,
            )

        # Update voice channel members cache
        if before_channel:
            # Remove user from previous channel
            if before_channel.id in self._voice_channel_members:
                self._voice_channel_members[before_channel.id].discard(member.id)
                # Clean up empty sets
                if not self._voice_channel_members[before_channel.id]:
                    del self._voice_channel_members[before_channel.id]

        if after_channel:
            # Add user to new channel
            if after_channel.id not in self._voice_channel_members:
                self._voice_channel_members[after_channel.id] = set()
            self._voice_channel_members[after_channel.id].add(member.id)

        # Handle leaving a managed channel - clean up if empty
        if before_channel and await self._is_managed_channel(before_channel.id):
            await self._handle_channel_left(before_channel, member)

        # Handle joining a join-to-create channel
        # Treat any move into a JTC (including from another JTC) as a join-to-create
        # but ignore reconnects to the same channel.
        is_jtc_after = False
        if after_channel:
            is_jtc_after = await self._is_join_to_create_channel(
                guild_id, after_channel.id
            )

        is_same_channel = (
            before_channel is not None
            and after_channel is not None
            and before_channel.id == after_channel.id
        )

        is_true_join = (
            after_channel is not None and is_jtc_after and not is_same_channel
        )

        # If the user came from a managed channel, allow bypassing cooldown so they can hop back to JTC immediately.
        bypass_cooldown = False
        if before_channel and await self._is_managed_channel(before_channel.id):
            bypass_cooldown = True

        if self.debug_logging_enabled:
            self.logger.info(
                "VS: classification guild=%s member=%s is_true_join=%s is_jtc_after=%s before_channel=%s",
                guild_id,
                getattr(member, "id", None),
                is_true_join,
                is_jtc_after,
                before_channel.name if before_channel else None,
            )

        if is_true_join and after_channel is not None:
            if self._is_user_creating(guild_id, member.id):
                if self.debug_logging_enabled:
                    self.logger.debug(
                        f"Skipping voice state update for {member.display_name} - creation in progress"
                    )
                return
            await self._handle_join_to_create(
                guild, after_channel, member, bypass_cooldown=bypass_cooldown
            )

    async def _is_managed_channel(self, channel_id: int) -> bool:
        """Check if a channel is managed by the bot."""
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1 LIMIT 1",
                    (channel_id,),
                )
                is_managed = await cursor.fetchone() is not None
                self.logger.debug(
                    f"Channel {channel_id} is {'managed' if is_managed else 'not managed'}"
                )
                return is_managed
        except Exception as e:
            self.logger.exception("Error checking if channel is managed", exc_info=e)
            return False

    async def _is_join_to_create_channel(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is a join-to-create channel."""
        try:
            jtc_channels = await self.config_service.get_guild_jtc_channels(guild_id)
            return channel_id in jtc_channels
        except Exception as e:
            self.logger.exception("Error checking if channel is JTC", exc_info=e)
            return False

    async def _handle_channel_left(
        self, channel: discord.VoiceChannel, member: discord.Member
    ) -> None:
        """Handle cleanup when a member leaves a managed channel."""
        try:
            self.logger.info(
                f"Member {member.display_name} left managed channel {channel.name} (ID: {channel.id})"
            )
            # Check if channel is now empty
            if len(channel.members) == 0:
                self.logger.info(
                    f"Channel {channel.name} (ID: {channel.id}) is now empty, performing immediate cleanup"
                )
                await self._cleanup_empty_channel(channel)
            else:
                self.logger.info(
                    f"Channel {channel.name} still has {len(channel.members)} members, no cleanup needed"
                )
        except Exception as e:
            self.logger.exception("Error handling channel left", exc_info=e)

    async def _notify_bot_spam_channel(
        self, guild: discord.Guild, message: str
    ) -> None:
        """Send a notification to the bot spam channel if configured."""
        try:
            bot_spam_channel_id = await self.config_service.get_guild_setting(
                guild.id, "channels.bot_spam_channel_id"
            )
            if bot_spam_channel_id:
                bot_spam_channel = guild.get_channel(bot_spam_channel_id)
                if bot_spam_channel and isinstance(
                    bot_spam_channel, discord.TextChannel
                ):
                    await bot_spam_channel.send(message)
                    self.logger.debug(
                        f"Sent notification to bot spam channel: {message}"
                    )
        except Exception as e:
            self.logger.warning(f"Failed to send bot spam channel notification: {e}")

    async def _send_settings_message_to_vc(
        self,
        voice_channel: discord.VoiceChannel,
        member: discord.Member,
        view: discord.ui.View,
    ) -> None:
        """Send the settings message to the voice channel via its send() method."""

        if self.debug_logging_enabled:
            self.logger.debug(
                "Sending settings message to VC %s for member %s",
                voice_channel.id,
                member.id,
            )

        try:
            await voice_channel.send(
                f"{member.mention}, configure your channel settings:",
                view=view,
            )

            if self.debug_logging_enabled:
                self.logger.debug(
                    "Successfully sent settings message to VC %s",
                    voice_channel.id,
                )
        except discord.Forbidden:
            self.logger.warning(
                f"Missing permissions to send settings message in VC {voice_channel.id}"
            )
        except discord.HTTPException as e:
            self.logger.warning(
                f"HTTP error sending settings message to VC {voice_channel.id}: {e}"
            )
        except Exception as e:
            self.logger.exception(
                f"Error sending VC settings message to {voice_channel.id}: {e}"
            )

    async def _cleanup_empty_channel(
        self, channel_or_id: discord.VoiceChannel | int
    ) -> None:
        """Immediately cleanup an empty managed channel."""
        # Determine channel_id and channel object
        if isinstance(channel_or_id, int):
            channel_id = channel_or_id
            channel = self.bot.get_channel(channel_id) if self.bot else None
        else:
            channel = channel_or_id
            channel_id = channel.id

        # If channel is None (already deleted), just clean up DB and cache
        if channel is None:
            self.logger.info(
                f"Channel {channel_id} already deleted, cleaning up DB and cache"
            )
            # Remove from managed channels set
            self.managed_voice_channels.discard(channel_id)

            # Remove from database
            try:
                await self.cleanup_by_channel_id(channel_id)
            except Exception as e:
                self.logger.exception(
                    "Error cleaning up channel %s in database", channel_id, exc_info=e
                )
            return

        # Channel exists, try to delete it
        try:
            # Delete the channel - handle idempotent 404 errors gracefully
            try:
                if isinstance(
                    channel,
                    (
                        discord.VoiceChannel,
                        discord.StageChannel,
                        discord.TextChannel,
                        discord.CategoryChannel,
                    ),
                ):
                    await channel.delete(reason="Empty managed voice channel cleanup")
                    self.logger.info(f"Successfully deleted empty channel {channel_id}")
                elif hasattr(channel, "delete"):
                    await cast("Any", channel).delete(
                        reason="Empty managed voice channel cleanup"
                    )
                    self.logger.info(f"Successfully deleted empty channel {channel_id}")
                else:
                    self.logger.warning(
                        f"Channel {channel_id} is not a deletable guild channel type, skipping"
                    )
                    return
            except discord.NotFound:
                # Channel already deleted - this is fine, no stack trace needed
                self.logger.info(f"Channel {channel_id} already deleted during cleanup")
            except discord.Forbidden as e:
                # Insufficient permissions - log warning and continue with cleanup
                self.logger.warning(
                    f"Insufficient permissions to delete channel {channel_id}: {e}, removing from tracking"
                )

        except Exception as e:
            self.logger.exception(
                "Unexpected error during channel deletion for %s",
                channel_id,
                exc_info=e,
            )
        finally:
            # Always remove from managed channels set and database
            self.managed_voice_channels.discard(channel_id)

            try:
                await self.cleanup_by_channel_id(channel_id)
                self.logger.info(f"Cleaned up tracking for channel {channel_id}")
            except Exception as e:
                self.logger.exception(
                    "Error cleaning up channel %s in database", channel_id, exc_info=e
                )

    async def _handle_join_to_create(
        self,
        guild: discord.Guild,
        jtc_channel: discord.VoiceChannel,
        member: discord.Member,
        *,
        bypass_cooldown: bool = False,
    ) -> None:
        """Handle join-to-create channel logic."""
        try:
            self.logger.info(
                f"{member.display_name} joined JTC channel {jtc_channel.name}"
            )

            if self.debug_logging_enabled:
                self.logger.info(
                    "JTC: handle_join guild=%s jtc=%s user=%s creating=%s",
                    guild.id,
                    jtc_channel.id,
                    member.id,
                    self._is_user_creating(guild.id, member.id),
                )

            if self._is_user_creating(guild.id, member.id):
                if self.debug_logging_enabled:
                    self.logger.debug(
                        f"Ignoring duplicate event for {member.display_name} - creation already in progress"
                    )
                return

            # Get per-user creation lock to prevent race conditions
            lock = await self._get_creation_lock(guild.id, member.id)

            if self.debug_logging_enabled:
                self.logger.debug(
                    f"Acquired per-user lock for {member.display_name} (ID: {member.id}) in guild {guild.id}"
                )

            creation_marked = False

            async with lock:
                if self._is_user_creating(guild.id, member.id):
                    if self.debug_logging_enabled:
                        self.logger.debug(
                            f"Skipping creation for {member.display_name}; lock-acquired dedupe"
                        )
                    return

                # Double-check cooldown after acquiring lock
                can_create, error_code = await self.can_create_voice_channel(
                    guild.id,
                    jtc_channel.id,
                    member.id,
                    bypass_cooldown=bypass_cooldown,
                )
                if not can_create:
                    # Check if it's because user is already creating
                    if error_code == "CREATING":
                        if self.debug_logging_enabled:
                            self.logger.debug(
                                f"Ignoring duplicate creation event for {member.display_name} - already creating"
                            )
                        return

                    self.logger.info(
                        f"Cooldown prevented channel creation for {member.display_name}: {error_code}"
                    )
                    # Parse cooldown seconds from error code (format: "COOLDOWN:5")
                    if error_code and error_code.startswith("COOLDOWN:"):
                        try:
                            seconds = int(error_code.split(":")[1])
                            from helpers.discord_reply import dm_user
                            from helpers.error_messages import format_user_error

                            message = format_user_error("COOLDOWN", seconds=seconds)
                            await dm_user(member, message)
                        except (ValueError, IndexError):
                            pass  # Ignore parsing errors
                    return

                # Mark user as creating to prevent duplicate events during channel creation
                self._mark_user_creating(guild.id, member.id)
                creation_marked = True

                if self.debug_logging_enabled:
                    self.logger.debug(
                        f"Marked user {member.id} as creating channel in guild {guild.id}"
                    )

                try:
                    # Create a new channel for the user with timeout
                    try:
                        channel: discord.VoiceChannel | None = None
                        if self.debug_logging_enabled:
                            self.logger.info(
                                "JTC: about_to_create guild=%s jtc=%s user=%s",
                                guild.id,
                                jtc_channel.id,
                                member.id,
                            )
                        channel = await asyncio.wait_for(
                            self._create_user_channel(guild, jtc_channel, member),
                            timeout=10.0,
                        )
                        if self.debug_logging_enabled:
                            self.logger.info(
                                "JTC: created_channel_result guild=%s jtc=%s user=%s channel=%s",
                                guild.id,
                                jtc_channel.id,
                                member.id,
                                channel.id if channel else None,
                            )
                    except TimeoutError:
                        self.logger.exception(
                            f"Channel creation timed out for {member.display_name} in JTC {jtc_channel.name}"
                        )
                        # Notify in bot spam channel
                        await self._notify_bot_spam_channel(
                            guild,
                            f"⚠️ Voice channel creation timed out for {member.mention} - Discord API may be slow",
                        )
                        # Send DM to user
                        try:
                            from helpers.discord_reply import dm_user

                            await dm_user(
                                member,
                                "⚠️ Voice channel creation took too long. Please try again.",
                            )
                        except Exception:
                            pass  # Ignore DM failures
                finally:
                    # Always unmark user as creating, even if creation fails
                    if creation_marked:
                        self._spawn_background_task(
                            self._delayed_unmark_user_creating(
                                guild.id,
                                member.id,
                                delay=self._creation_unmark_delay,
                            ),
                            name=f"voice.unmark_user.{guild.id}.{member.id}",
                        )

        except Exception as e:
            self.logger.exception("Error handling join-to-create", exc_info=e)

    async def _create_user_channel(
        self,
        guild: discord.Guild,
        jtc_channel: discord.VoiceChannel,
        member: discord.Member,
    ) -> discord.VoiceChannel | None:
        """Create a new voice channel for a user and return it on success.

        This is the AUTHORITATIVE channel creation path. All voice channel creation
        must route through this function to ensure proper race-condition handling,
        atomic DB operations, and consistent permission enforcement.

        DO NOT call guild.create_voice_channel() directly elsewhere - use this function
        or _handle_join_to_create() which calls this function.
        """
        try:
            self.logger.info(
                f"Creating channel for {member.display_name} (ID: {member.id}) in guild {guild.id}, JTC channel {jtc_channel.id} ('{jtc_channel.name}')"
            )

            # Load saved settings from database
            saved_settings = await self._load_channel_settings(
                guild.id, jtc_channel.id, member.id
            )

            # Debug logging to see what settings are loaded
            if self.debug_logging_enabled:
                if saved_settings:
                    self.logger.debug(
                        f"Loaded settings for user {member.id} in JTC {jtc_channel.id}: {len(saved_settings)} settings"
                    )
                else:
                    self.logger.debug(
                        f"No saved settings found for user {member.id} in JTC {jtc_channel.id}"
                    )

            # Generate channel name - use saved name if available, otherwise default
            if saved_settings and saved_settings.get("channel_name"):
                channel_name = saved_settings["channel_name"]
                if self.debug_logging_enabled:
                    self.logger.debug(f"Using saved channel name for user {member.id}")
            else:
                channel_name = f"{member.display_name}'s Channel"
                if self.debug_logging_enabled:
                    self.logger.debug(
                        f"Using default channel name for user {member.id}"
                    )

            # Create the channel in the same category as the JTC channel
            category = jtc_channel.category

            # Determine user limit - use saved limit if available, otherwise JTC default
            if saved_settings and saved_settings.get("user_limit") is not None:
                user_limit = saved_settings["user_limit"]
            else:
                user_limit = jtc_channel.user_limit

            # Check permissions before attempting to create channel
            if category is None:
                raise RuntimeError(f"JTC channel {jtc_channel.name} has no category")

            if not self.bot or not self.bot.user:
                raise RuntimeError("Bot instance or bot user not available")

            bot_member = guild.get_member(self.bot.user.id)
            if bot_member is None:
                raise RuntimeError("Bot member not found in guild")

            # Check if bot has permissions to create channels in the category
            perms = category.permissions_for(bot_member)
            if not perms.manage_channels:
                error_msg = f"Bot missing 'Manage Channels' permission in category '{category.name}'"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)

            # Create the channel without overwrites to inherit from parent category
            channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                bitrate=jtc_channel.bitrate,
                user_limit=user_limit,
            )

            # Set user permissions only if bot's role is higher than member's role
            try:
                # For mock objects, top_role comparison may fail - catch and skip
                try:
                    role_check = bot_member.top_role > member.top_role
                except (TypeError, AttributeError):
                    # Mock objects or missing attributes - assume permission check passes
                    role_check = True

                if role_check:
                    await channel.set_permissions(
                        member,
                        connect=True,
                        manage_channels=True,
                    )
                    self.logger.debug(
                        f"Set user permissions for {member.display_name} on channel {channel.name}"
                    )
                else:
                    self.logger.warning(
                        f"Skipping permission override for {member.display_name} - bot role '{bot_member.top_role.name}' "
                        f"is not higher than member role '{member.top_role.name}'"
                    )
            except discord.Forbidden as e:
                self.logger.warning(
                    f"Could not set permissions for {member.display_name}: {e}"
                )
            except Exception as e:
                self.logger.exception(
                    f"Unexpected error setting permissions for {member.display_name}: {e}"
                )

            # Apply all saved settings from database after creation
            if self.bot:
                await enforce_permission_changes(
                    channel=channel,
                    bot=self.bot,
                    user_id=member.id,
                    guild_id=guild.id,
                    jtc_channel_id=jtc_channel.id,
                )

            # Validate user is still connected to voice before moving
            if member.voice is None or member.voice.channel is None:
                self.logger.warning(
                    f"User {member.display_name} disconnected before channel creation completed, cleaning up channel {channel.id}"
                )
                # Cleanup the created channel
                try:
                    await channel.delete(
                        reason="User disconnected during channel creation"
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup channel {channel.id}: {e}")

                # Send DM to user
                try:
                    from helpers.discord_reply import dm_user

                    await dm_user(
                        member,
                        "⚠️ Your voice channel was created but you disconnected before it was ready. Please rejoin the Join to Create channel to try again.",
                    )
                except Exception:
                    pass  # Ignore DM failures

                # Notify in bot spam channel
                await self._notify_bot_spam_channel(
                    guild,
                    f"⚠️ Voice channel creation aborted for {member.mention} - user disconnected during setup",
                )
                return None

            # Move the user to their new channel BEFORE storing in database
            # This prevents race conditions where concurrent operations see the channel
            # as active before the user is actually in it
            try:
                await member.move_to(channel)
            except discord.HTTPException as e:
                self.logger.exception(
                    f"Failed to move {member.display_name} to channel {channel.id}: {e}"
                )
                # Cleanup the created channel
                try:
                    await channel.delete(reason="Failed to move user")
                    self.logger.info(
                        f"Cleaned up channel {channel.id} after failed move"
                    )
                except Exception as cleanup_error:
                    self.logger.warning(
                        f"Failed to cleanup channel {channel.id}: {cleanup_error}"
                    )

                # Send DM to user
                try:
                    from helpers.discord_reply import dm_user

                    await dm_user(
                        member,
                        "⚠️ Failed to move you to your voice channel. You may have disconnected too quickly. Please try again.",
                    )
                except Exception:
                    pass  # Ignore DM failures

                # Notify in bot spam channel
                await self._notify_bot_spam_channel(
                    guild,
                    f"⚠️ Voice channel creation failed for {member.mention} - could not move user (error: {e})",
                )
                return None

            # Only store in database after successful move
            await self._store_user_channel(
                guild.id, jtc_channel.id, member.id, channel.id
            )

            # Update cooldown
            await self._update_cooldown(guild.id, jtc_channel.id, member.id)

            # Update last used JTC channel for deterministic settings behavior
            await update_last_used_jtc_channel(guild.id, member.id, jtc_channel.id)

            # Add to managed channels set
            self.managed_voice_channels.add(channel.id)

            self.logger.info(
                f"Created channel '{channel.name}' for {member.display_name}"
            )

            # Send channel settings view message
            try:
                # Late import to break circular dependency between voice_service and views
                # (views imports voice utilities which depend on voice_service)
                from helpers.views import ChannelSettingsView

                await self._send_settings_message_to_vc(
                    voice_channel=channel,
                    member=member,
                    view=ChannelSettingsView(self.bot),
                )
            except Exception as e:
                self.logger.exception(
                    f"Error sending settings view to '{channel.name}': {e}"
                )

            return channel

        except discord.Forbidden as e:
            # Specific handling for permission errors
            if "50013" in str(e) or "Missing Permissions" in str(e):
                self.logger.exception(
                    f"Permission denied creating channel for {member.display_name} in '{jtc_channel.category.name if jtc_channel.category else 'no category'}': {e}"
                )
                try:
                    await member.send(
                        f"❌ I don't have permission to create voice channels in the **{jtc_channel.category.name if jtc_channel.category else 'current'}** category. "
                        "Please ask a server admin to give me the 'Manage Channels' permission in that category."
                    )
                except Exception:
                    pass  # Ignore if we can't send DM
                return None  # Stop execution as channel creation failed
            else:
                self.logger.exception(
                    "Discord permission error creating user channel", exc_info=e
                )
                return None
        except Exception as e:
            self.logger.exception("Error creating user channel", exc_info=e)
            return None

    def _get_user_game_name(self, member: discord.Member) -> str | None:
        """Get the user's current game/activity name."""
        try:
            if member.activity and hasattr(member.activity, "name"):
                return member.activity.name
        except Exception:
            pass
        return None

    async def _handle_old_channel_transition(
        self,
        *,
        db: Any,
        guild_id: int,
        jtc_channel_id: int,
        user_id: int,
        old_channel_id: int,
        new_channel_id: int,
    ) -> discord.VoiceChannel | None:
        """
        Handle transition when a user already has an active channel.

        Returns orphaned channel object when ownership is cleared but members remain.
        """

        old_channel_candidate = (
            self.bot.get_channel(old_channel_id) if self.bot else None
        )
        # Support both real discord channels and mock objects with voice channel interface
        old_channel: discord.VoiceChannel | discord.StageChannel | None = None
        if isinstance(old_channel_candidate, (discord.VoiceChannel, discord.StageChannel)):
            old_channel = old_channel_candidate
        elif (
            old_channel_candidate
            and hasattr(old_channel_candidate, "members")
            and hasattr(old_channel_candidate, "edit")
            and hasattr(old_channel_candidate, "overwrites")
        ):
            # Mock object with voice channel interface - cast for type safety
            old_channel = cast("discord.VoiceChannel", old_channel_candidate)

        member_count = self._get_voice_channel_member_count(
            old_channel or old_channel_id
        )

        if self.debug_logging_enabled:
            self.logger.info(
                "DB: decision guild=%s jtc=%s user=%s old_channel=%s new_channel=%s has_members=%s",
                guild_id,
                jtc_channel_id,
                user_id,
                old_channel_id,
                new_channel_id,
                member_count > 0,
            )

        if member_count > 0:
            await db.execute(
                """
                UPDATE voice_channels
                SET owner_id = ?, previous_owner_id = ?, last_activity = ?, is_active = 1
                WHERE voice_channel_id = ?
            """,
                (
                    self.ORPHAN_OWNER_ID,
                    user_id,
                    int(time.time()),
                    old_channel_id,
                ),
            )

            if isinstance(old_channel, discord.VoiceChannel):
                return old_channel
            if hasattr(old_channel, "edit") and hasattr(old_channel, "overwrites"):
                return cast("discord.VoiceChannel", old_channel)
            return None

        # No members remaining: remove rows and schedule cleanup
        await db.execute(
            "DELETE FROM voice_channel_settings WHERE voice_channel_id = ?",
            (old_channel_id,),
        )
        await db.execute(
            "DELETE FROM voice_channels WHERE voice_channel_id = ?",
            (old_channel_id,),
        )

        if member_count == 0:
            cleanup_target: discord.VoiceChannel | int | None
            cleanup_target = (
                old_channel
                if isinstance(old_channel, discord.VoiceChannel)
                else old_channel_id
            )
            if cleanup_target is not None:
                self._spawn_background_task(
                    self._cleanup_empty_channel(cleanup_target),
                    name=f"voice.cleanup_old_channel.{old_channel_id}",
                )

        return None

    async def _store_user_channel(
        self, guild_id: int, jtc_channel_id: int, user_id: int, channel_id: int
    ) -> None:
        """Store user channel in database with atomic transaction to prevent duplicates.

        Uses explicit transaction with SELECT + INSERT to ensure only one active channel
        per user per JTC exists in the database, preventing TOCTOU race conditions.
        """
        try:
            orphaned_channel: discord.VoiceChannel | None = None
            async with Database.get_connection() as db:
                # Begin explicit transaction for atomicity
                await db.execute("BEGIN EXCLUSIVE TRANSACTION")

                try:
                    # Check if there's already an active channel for this user in this JTC
                    # This SELECT happens inside the transaction, preventing TOCTOU
                    cursor = await db.execute(
                        """
                        SELECT voice_channel_id FROM voice_channels
                        WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
                    """,
                        (guild_id, jtc_channel_id, user_id),
                    )
                    existing_row = await cursor.fetchone()
                    existing_channel_id = existing_row[0] if existing_row else None

                    if self.debug_logging_enabled:
                        self.logger.info(
                            "DB: store_user_channel guild=%s jtc=%s user=%s existing_channel=%s",
                            guild_id,
                            jtc_channel_id,
                            user_id,
                            existing_channel_id,
                        )

                    if existing_row and existing_channel_id is not None:
                        old_channel_id = existing_channel_id
                        if old_channel_id == channel_id:
                            # Same channel, this is a no-op (defensive check)
                            if self.debug_logging_enabled:
                                self.logger.debug(
                                    f"DB: Channel {channel_id} already stored for user {user_id}, skipping duplicate insert"
                                )
                            await db.commit()
                            return

                        orphaned_channel = await self._handle_old_channel_transition(
                            db=db,
                            guild_id=guild_id,
                            jtc_channel_id=jtc_channel_id,
                            user_id=user_id,
                            old_channel_id=old_channel_id,
                            new_channel_id=channel_id,
                        )

                    # Insert the new channel atomically
                    await db.execute(
                        """
                        INSERT INTO voice_channels
                        (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            guild_id,
                            jtc_channel_id,
                            user_id,
                            channel_id,
                            int(time.time()),
                            int(time.time()),
                            1,
                        ),
                    )

                    # Commit transaction
                    await db.commit()

                    if self.debug_logging_enabled:
                        self.logger.info(
                            "DB: insert_complete guild=%s jtc=%s user=%s old_channel=%s new_channel=%s",
                            guild_id,
                            jtc_channel_id,
                            user_id,
                            existing_channel_id,
                            channel_id,
                        )

                except Exception as e:
                    # Rollback on any error
                    await db.rollback()
                    self.logger.exception(
                        f"Transaction rolled back during channel storage: {e}"
                    )
                    raise

        except Exception as e:
            self.logger.exception("Error storing user channel", exc_info=e)
            orphaned_channel = None  # Ensure it's defined even if exception occurred

        # Remove owner overwrites after transaction commits to avoid blocking DB
        if orphaned_channel:
            await self._remove_owner_overwrites(orphaned_channel, user_id)

    async def _remove_owner_overwrites(
        self, channel: discord.VoiceChannel, owner_id: int
    ) -> None:
        """Strip owner-specific overwrites so the channel truly becomes ownerless."""
        if not channel or not hasattr(channel, "guild"):
            return

        try:
            member = channel.guild.get_member(owner_id)
            if not member:
                return

            # Support both VoiceChannel and mock objects
            if hasattr(channel, "overwrites") and hasattr(channel, "edit"):
                overwrites = (
                    channel.overwrites.copy()
                    if hasattr(channel.overwrites, "copy")
                    else dict(channel.overwrites)
                )
                if member in overwrites:
                    overwrites.pop(member, None)
                    await channel.edit(overwrites=overwrites)
                    if self.debug_logging_enabled:
                        self.logger.info(
                            "Removed overwrites for previous owner %s on orphaned channel %s",
                            owner_id,
                            channel.id,
                        )
        except Exception as exc:
            self.logger.warning(
                "Failed to remove overwrites for owner %s on channel %s: %s",
                owner_id,
                getattr(channel, "id", "unknown"),
                exc,
            )

    async def _schedule_channel_cleanup(self, channel_id: int) -> None:
        """Schedule cleanup of an empty channel after a delay (fallback for ambiguous cases)."""

        # Get configurable delay from config, default to 10 seconds
        delete_delay = await self.config_service.get_global_setting(
            "voice.delete_delay_seconds", 10
        )

        # Capture references for the cleanup task
        bot = self.bot
        logger = self.logger

        async def cleanup_after_delay():
            await asyncio.sleep(delete_delay)

            try:
                if not bot:
                    logger.warning(
                        f"No bot instance for cleanup of channel {channel_id}"
                    )
                    return

                channel = bot.get_channel(channel_id)
                voice_like: discord.VoiceChannel | None = None
                if isinstance(channel, discord.VoiceChannel):
                    voice_like = channel
                elif hasattr(channel, "members") and hasattr(channel, "delete"):
                    voice_like = cast("discord.VoiceChannel", channel)

                if voice_like and len(voice_like.members) == 0:
                    # Use the same cleanup path as immediate cleanup
                    await self._cleanup_empty_channel(voice_like)
                elif channel:
                    logger.info(
                        f"Channel {channel_id} no longer empty, skipping cleanup"
                    )
                else:
                    # Channel already deleted or missing, pass channel_id for cleanup
                    await self._cleanup_empty_channel(channel_id)

            except Exception as e:
                logger.exception("Error during scheduled cleanup", exc_info=e)

        # Schedule the cleanup
        self._spawn_background_task(
            cleanup_after_delay(),
            name=f"voice.cleanup_after_delay.{channel_id}",
        )

    async def _run_reconcile_after_ready(self) -> None:
        """Run reconciliation after bot is ready with configurable delay."""
        try:
            # Wait for bot to be ready
            if self.bot:
                if not hasattr(self.bot, "guilds") or not isinstance(
                    self.bot.guilds, Iterable
                ):
                    self.logger.warning(
                        "Bot guilds collection missing or not iterable; skipping startup reconciliation scheduling"
                    )
                    return

                await self.bot.wait_until_ready()

                # Get configurable delay, default to 2000ms (2 seconds)
                delay_ms = await self.config_service.get_global_setting(
                    "voice.startup_delay_ms", 2000
                )
                await asyncio.sleep(delay_ms / 1000.0)

                # Run the reconciliation
                await self.reconcile_all_guilds_on_ready()

                # After reconciliation, move members back to existing channels (no new creation)
                self._spawn_background_task(
                    self._reconcile_jtc_members_on_startup(),
                    name="voice.reconcile_jtc_members_on_startup",
                )
            else:
                self.logger.warning(
                    "Bot instance not available for startup reconciliation"
                )
        except Exception as e:
            self.logger.exception("Error during startup reconciliation", exc_info=e)

    async def _reconcile_jtc_members_on_startup(self) -> None:
        """
        Reconcile members in JTC channels after bot restart.

        DOES NOT create new channels. Only moves users back to existing channels
        if they have one. Users without existing channels must rejoin the JTC
        channel to trigger creation (prevents startup spam and race conditions).
        """
        try:
            # Ensure bot is ready
            if not self.bot:
                self.logger.warning(
                    "Bot instance not available for JTC member reconciliation"
                )
                return

            await self.bot.wait_until_ready()

            if not hasattr(self.bot, "guilds") or not isinstance(
                self.bot.guilds, Iterable
            ):
                self.logger.warning(
                    "Bot guilds collection missing or not iterable; skipping JTC member reconciliation"
                )
                return

            self.logger.info(
                "Reconciling JTC channel members (no new channel creation)..."
            )

            total_moved = 0
            total_skipped = 0
            total_errors = 0

            # Process each guild the bot is in
            for guild in self.bot.guilds:
                try:
                    # Get JTC channel IDs for this guild
                    jtc_ids = await self.config_service.get_guild_jtc_channels(guild.id)

                    if not jtc_ids:
                        continue

                    # Process each JTC channel
                    for jtc_id in jtc_ids:
                        try:
                            # Try to get channel from cache first, then fetch
                            vc = guild.get_channel(jtc_id)
                            if not vc:
                                try:
                                    vc = await self.bot.fetch_channel(jtc_id)
                                except discord.NotFound:
                                    self.logger.warning(
                                        f"JTC channel {jtc_id} no longer exists in guild {guild.name}"
                                    )
                                    continue
                                except Exception as e:
                                    self.logger.warning(
                                        f"Failed to fetch JTC channel {jtc_id} in guild {guild.name}: {e}"
                                    )
                                    continue

                            # Ensure it's a voice channel
                            if not isinstance(vc, discord.VoiceChannel):
                                self.logger.warning(
                                    f"JTC channel {jtc_id} in guild {guild.name} is not a voice channel"
                                )
                                continue

                            # Process each human member in the JTC channel
                            for member in list(
                                vc.members
                            ):  # Use list() to avoid iteration issues during moves
                                if member.bot:
                                    continue  # Skip bots

                                try:
                                    # Check if user has an existing active channel for this JTC
                                    async with Database.get_connection() as db:
                                        cursor = await db.execute(
                                            """
                                            SELECT voice_channel_id FROM voice_channels
                                            WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
                                            LIMIT 1
                                        """,
                                            (guild.id, jtc_id, member.id),
                                        )
                                        row = await cursor.fetchone()

                                    if row:
                                        existing_channel_id = row[0]
                                        existing_channel = guild.get_channel(
                                            existing_channel_id
                                        )

                                        if existing_channel and isinstance(
                                            existing_channel, discord.VoiceChannel
                                        ):
                                            # Move user back to their existing channel
                                            try:
                                                await member.move_to(existing_channel)
                                                self.logger.info(
                                                    f"Moved {member.display_name} back to existing channel {existing_channel.name}"
                                                )
                                                total_moved += 1
                                            except discord.HTTPException as e:
                                                self.logger.warning(
                                                    f"Failed to move {member.display_name} to existing channel: {e}"
                                                )
                                                total_errors += 1
                                        else:
                                            # Channel in DB but doesn't exist in Discord - clean up
                                            self.logger.info(
                                                f"Cleaning up stale channel reference {existing_channel_id} for user {member.id}"
                                            )
                                            await self.cleanup_by_channel_id(
                                                existing_channel_id
                                            )
                                            total_skipped += 1
                                    else:
                                        # No existing channel - user must rejoin JTC to create one
                                        if self.debug_logging_enabled:
                                            self.logger.debug(
                                                f"User {member.display_name} has no existing channel, must rejoin JTC to create"
                                            )
                                        total_skipped += 1

                                except Exception as e:
                                    self.logger.exception(
                                        f"Failed to reconcile {member.display_name} ({member.id}) in JTC {jtc_id}",
                                        exc_info=e,
                                    )
                                    total_errors += 1

                        except Exception as e:
                            self.logger.exception(
                                f"Error processing JTC channel {jtc_id} in guild {guild.name}",
                                exc_info=e,
                            )
                            total_errors += 1

                except Exception as e:
                    self.logger.exception(
                        f"Error processing guild {guild.name} ({guild.id}) for JTC reconciliation",
                        exc_info=e,
                    )

            self.logger.info(
                f"JTC member reconciliation complete: {total_moved} moved to existing channels, "
                f"{total_skipped} skipped (no existing channel), {total_errors} errors"
            )

        except Exception as e:
            self.logger.exception("Error during JTC member reconciliation", exc_info=e)

    async def reconcile_all_guilds_on_ready(self) -> None:
        """
        Reconcile all user voice channels after bot ready and member chunking.


        For each guild the bot is in:
        - Fetch all rows from voice_channels
        - Check if channels still exist
        - If not exists → remove DB row
        - If exists and has members or owner connected → keep and rehydrate management
        - If exists but empty → schedule deletion with delay
        """
        if not self.bot:
            self.logger.warning("Bot instance not available for reconciliation")
            return

        self.logger.info("Starting voice channel reconciliation across all guilds")

        deleted_inactive = await self._purge_inactive_voice_channels()
        if deleted_inactive:
            self.logger.info(
                f"Purged {deleted_inactive} inactive voice channel rows before reconciliation"
            )

        total_reconciled = 0
        total_removed = 0
        total_rehydrated = 0
        total_scheduled_cleanup = 0

        try:
            async with Database.get_connection() as db:
                # Fetch all user voice channels across all guilds
                cursor = await db.execute(
                    """SELECT guild_id, voice_channel_id, owner_id, jtc_channel_id, created_at
                       FROM voice_channels WHERE is_active = 1"""
                )
                all_channels = await cursor.fetchall()

                for (
                    guild_id,
                    voice_channel_id,
                    owner_id,
                    jtc_channel_id,
                    created_at,
                ) in all_channels:
                    try:
                        await self._reconcile_single_channel(
                            guild_id,
                            voice_channel_id,
                            owner_id,
                            jtc_channel_id,
                            created_at,
                        )
                        total_reconciled += 1

                        # Track reconciliation results based on what happened
                        channel = self.bot.get_channel(voice_channel_id)
                        if not channel:
                            total_removed += 1
                        elif voice_channel_id in self.managed_voice_channels:
                            total_rehydrated += 1
                        else:
                            total_scheduled_cleanup += 1

                    except Exception as e:
                        self.logger.exception(
                            f"Error reconciling channel {voice_channel_id} (guild {guild_id})",
                            exc_info=e,
                        )

        except Exception as e:
            self.logger.exception(
                "Error during voice channel reconciliation", exc_info=e
            )

        self.logger.info(
            f"Voice channel reconciliation complete: {total_reconciled} channels processed, "
            f"{total_removed} removed, {total_rehydrated} rehydrated, {total_scheduled_cleanup} scheduled for cleanup"
        )

    async def _reconcile_single_channel(
        self,
        guild_id: int,
        voice_channel_id: int,
        owner_id: int,
        jtc_channel_id: int,
        created_at: int,
    ) -> None:
        """
        Reconcile a single voice channel during startup.

        Args:
            guild_id: Discord guild ID
            voice_channel_id: Voice channel ID to reconcile
            owner_id: Channel owner ID
            jtc_channel_id: JTC channel ID this channel belongs to
            created_at: Timestamp when channel was created
        """
        # Try to get the channel, first from cache then fetch
        if not self.bot:
            self.logger.warning("Bot instance not available for reconciliation")
            await self.cleanup_by_channel_id(voice_channel_id)
            return

        channel = self.bot.get_channel(voice_channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(voice_channel_id)
            except discord.NotFound:
                channel = None
            except Exception as e:
                self.logger.warning(f"Failed to fetch channel {voice_channel_id}: {e}")
                channel = None

        # Channel no longer exists - remove DB row
        if not channel:
            self.logger.info(f"Removing stale channel {voice_channel_id} from database")
            await self.cleanup_by_channel_id(voice_channel_id)
            return

        # Channel still exists - determine what to do based on emptiness and ownership
        if not isinstance(channel, discord.VoiceChannel):
            self.logger.warning(
                f"Channel {voice_channel_id} is not a VoiceChannel, removing from database"
            )
            await self.cleanup_by_channel_id(voice_channel_id)
            return

        should_keep_active = await self._should_keep_channel_active(channel, owner_id)

        if should_keep_active:
            # Add to managed channels and rehydrate settings when we still have an owner
            self.managed_voice_channels.add(voice_channel_id)
            if owner_id != self.ORPHAN_OWNER_ID:
                await self._rehydrate_channel_management(
                    channel, owner_id, jtc_channel_id, guild_id
                )
                self.logger.info(
                    f"Rehydrated channel {voice_channel_id} for owner {owner_id} with {len(channel.members)} members."
                )
            else:
                self.logger.info(
                    f"Skipped rehydration for orphaned channel {voice_channel_id}; members will need to claim ownership."
                )
        else:
            # Check startup cleanup mode (immediate vs delayed)
            startup_cleanup_mode = await self.config_service.get_global_setting(
                "voice.startup_cleanup_mode", "delayed"
            )

            if startup_cleanup_mode == "immediate":
                channel_name = getattr(channel, "name", str(voice_channel_id))
                self.logger.info(
                    f"Immediately cleaning up empty channel {channel_name} ({voice_channel_id}) per startup_cleanup_mode"
                )
                await self._cleanup_empty_channel(voice_channel_id)
            else:
                # Schedule deletion with delay to handle race conditions
                channel_name = getattr(channel, "name", str(voice_channel_id))
                self.logger.info(
                    f"Scheduling cleanup for empty channel {channel_name} ({voice_channel_id})"
                )
                await self._schedule_channel_cleanup(voice_channel_id)

    async def _should_keep_channel_active(
        self, channel: discord.VoiceChannel, owner_id: int
    ) -> bool:
        """
        Determine if a channel should be kept active during reconciliation.

        Returns True if:
        - Channel has members, OR
        - Channel owner is actually connected to that channel
        """
        # Check if channel has any members
        if len(channel.members) > 0:
            return True

        # Check if owner is connected to this specific channel
        try:
            guild = channel.guild
            owner = guild.get_member(owner_id)
            if (
                owner
                and owner.voice
                and owner.voice.channel
                and owner.voice.channel.id == channel.id
            ):
                return True
        except Exception as e:
            self.logger.warning(
                f"Error checking owner connection for channel {channel.id}: {e}"
            )

        return False

    async def _rehydrate_channel_management(
        self,
        channel: discord.VoiceChannel,
        owner_id: int,
        jtc_channel_id: int,
        guild_id: int,
    ) -> None:
        """
        Rehydrate channel management by applying stored settings and permissions.

        Args:
            channel: Discord voice channel
            owner_id: Channel owner ID
            jtc_channel_id: JTC channel ID
            guild_id: Guild ID
        """
        try:
            # Late import to break circular dependency between voice_service and voice_permissions
            # (voice_permissions imports discord_api which may depend on voice_service)
            from helpers.voice_permissions import enforce_permission_changes

            # Re-apply channel overwrites/settings using existing helpers
            # Signature: enforce_permission_changes(channel, bot, user_id, guild_id, jtc_channel_id)
            if self.bot:
                await enforce_permission_changes(
                    channel, self.bot, owner_id, guild_id, jtc_channel_id
                )

            self.logger.info(
                f"Applied permission overwrites for channel {channel.name} ({channel.id}) owner {owner_id}"
            )

        except Exception as e:
            self.logger.exception(
                f"Error rehydrating channel management for {channel.id}", exc_info=e
            )

    async def initialize_guild_voice_channels(self, guild_id: int) -> None:
        """
        Initialize voice channel settings for a guild.

        Validates that configured join-to-create (JTC) channels exist in the guild.
        Logs warnings for missing channels but does not create them automatically.

        Args:
            guild_id: Discord guild ID to initialize voice channels for
        """
        self.logger.info(f"Initializing voice channels for guild {guild_id}")

        if not self.bot:
            self.logger.warning(
                f"Bot instance not available for guild {guild_id} voice initialization"
            )
            return

        # Get the guild object
        guild = self.bot.get_guild(guild_id)
        if not guild:
            self.logger.warning(
                f"Guild {guild_id} not found for voice channel initialization"
            )
            return

        try:
            # Get configured JTC channels for this guild
            jtc_channel_ids = await self._get_guild_jtc_channels(guild_id)

            if not jtc_channel_ids:
                self.logger.info(
                    f"No JTC channels configured for guild {guild.name} ({guild_id})"
                )
                return

            # Validate each configured JTC channel exists
            missing_channels = []
            existing_channels = []

            for channel_id in jtc_channel_ids:
                channel = guild.get_channel(channel_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    existing_channels.append(channel_id)
                else:
                    missing_channels.append(channel_id)

            # Log results
            if existing_channels:
                self.logger.info(
                    f"Found {len(existing_channels)} valid JTC channels in guild {guild.name}"
                )

            if missing_channels:
                self.logger.warning(
                    f"Missing {len(missing_channels)} configured JTC channels in guild {guild.name}: {missing_channels}"
                )

            self.logger.info(
                f"Voice channel initialization completed for guild {guild.name} ({guild_id})"
            )

        except Exception as e:
            self.logger.exception(
                f"Error initializing voice channels for guild {guild_id}", exc_info=e
            )

    async def _get_guild_jtc_channels(self, guild_id: int) -> list[int]:
        """Get join-to-create channel IDs for a guild."""
        try:
            return await self.config_service.get_guild_jtc_channels(guild_id)
        except Exception as e:
            self.logger.exception("Error getting JTC channels", exc_info=e)
            return []

    async def _load_channel_settings(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """
        Load saved channel settings for a user from the database.

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            user_id: Discord user ID

        Returns:
            Dictionary of settings or None if no settings exist
        """
        try:
            self.logger.debug(
                f"Loading channel settings for user {user_id} in guild {guild_id}, JTC {jtc_channel_id}"
            )
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT channel_name, user_limit, lock
                    FROM channel_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, user_id),
                )
                row = await cursor.fetchone()

                if not row:
                    self.logger.debug(
                        f"No settings row found for user {user_id}, guild {guild_id}, JTC {jtc_channel_id}"
                    )
                    return None

                channel_name, user_limit, lock = row
                result = {
                    "channel_name": channel_name,
                    "user_limit": user_limit,
                    "lock": lock,
                }
                self.logger.debug(f"Found settings: {result}")
                return result

        except Exception as e:
            self.logger.exception("Error loading channel settings", exc_info=e)
            return None

    async def get_user_channel_settings(
        self, guild_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """
        Get all settings for a user's voice channel.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Dictionary of settings or None if no settings exist
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT setting_key, setting_value
                    FROM voice_channel_settings
                    WHERE guild_id = ? AND owner_id = ?
                """,
                    (guild_id, user_id),
                )
                rows = await cursor.fetchall()

                if not rows:
                    return None

                return {row[0]: row[1] for row in rows}

        except Exception as e:
            self.logger.exception("Error getting user channel settings", exc_info=e)
            return None

    async def create_settings_list_embed(
        self, guild_id: int, user_id: int, settings: dict[str, Any]
    ) -> discord.Embed:
        """
        Create an embed showing a user's voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            settings: Settings dictionary

        Returns:
            Discord embed with formatted settings
        """
        embed = discord.Embed(
            title="🎙️ Your Voice Channel Settings", color=discord.Color.blue()
        )

        if not settings:
            embed.description = "No custom settings configured."
            return embed

        # Format settings nicely
        settings_text = []
        for key, value in settings.items():
            formatted_key = key.replace("_", " ").title()
            settings_text.append(f"**{formatted_key}:** {value}")

        embed.add_field(
            name="Current Settings",
            value="\n".join(settings_text) if settings_text else "None",
            inline=False,
        )

        return embed

    async def claim_voice_channel(
        self, guild_id: int, user_id: int, user: discord.Member
    ) -> VoiceChannelResult:
        """
        Claim ownership of a voice channel if the current owner is absent.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            user: Discord member object

        Returns:
            VoiceChannelResult with success status and error code (not formatted message)
        """
        try:
            # Check if user is in a voice channel
            if not user.voice or not user.voice.channel:
                return VoiceChannelResult(
                    success=False,
                    error="NOT_IN_VOICE",
                )

            channel = user.voice.channel

            # Check if this is a managed voice channel from voice_channels
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT owner_id, previous_owner_id, jtc_channel_id
                    FROM voice_channels
                    WHERE guild_id = ? AND voice_channel_id = ? AND is_active = 1
                """,
                    (guild_id, channel.id),
                )
                row = await cursor.fetchone()

                if not row:
                    return VoiceChannelResult(success=False, error="NOT_MANAGED")

                current_owner_id, previous_owner_id, jtc_channel_id = row
                ownerless = current_owner_id == self.ORPHAN_OWNER_ID
                effective_previous_owner = (
                    previous_owner_id
                    if ownerless and previous_owner_id
                    else current_owner_id
                )

                # Check if current owner is still in the channel (skip for orphaned channels)
                if not ownerless:
                    current_owner = channel.guild.get_member(current_owner_id)
                    if current_owner and current_owner in channel.members:
                        return VoiceChannelResult(
                            success=False,
                            error="OWNER_PRESENT",
                        )

                # Use the comprehensive transfer method from voice_repo
                from helpers.voice_repo import transfer_channel_owner

                success = await transfer_channel_owner(
                    voice_channel_id=channel.id,
                    new_owner_id=user_id,
                    guild_id=guild_id,
                    jtc_channel_id=jtc_channel_id,
                )

                if not success:
                    return VoiceChannelResult(
                        success=False,
                        error="DB_TEMP_ERROR",
                    )

                # Update permission overwrites using permissions helper

                from helpers.permissions_helper import update_channel_owner

                # Cast for type-checker: allow voice or stage channels.
                channel_for_perms = cast(
                    "discord.VoiceChannel | discord.StageChannel", channel
                )

                # Rely on duck typing so test doubles (MockVoiceChannel) still exercise the path.
                await update_channel_owner(
                    channel=channel_for_perms,
                    new_owner_id=user_id,
                    previous_owner_id=effective_previous_owner,
                    guild_id=guild_id,
                    jtc_channel_id=jtc_channel_id,
                )

            return VoiceChannelResult(
                success=True, channel_id=channel.id, channel_mention=channel.mention
            )

        except Exception as e:
            self.logger.exception("Error claiming voice channel", exc_info=e)
            return VoiceChannelResult(success=False, error="UNKNOWN")

    async def transfer_voice_channel_ownership(
        self,
        guild_id: int,
        current_owner_id: int,
        new_owner_id: int,
        new_owner: discord.Member,
    ) -> VoiceChannelResult:
        """
        Transfer ownership of a voice channel to another user.

        Args:
            guild_id: Discord guild ID
            current_owner_id: Current owner's user ID
            new_owner_id: New owner's user ID
            new_owner: New owner member object

        Returns:
            VoiceChannelResult with success status and error code (not formatted message)
        """
        try:
            async with Database.get_connection() as db:
                # Find the user's voice channel from voice_channels table
                cursor = await db.execute(
                    """
                    SELECT voice_channel_id, jtc_channel_id FROM voice_channels
                    WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                    ORDER BY created_at DESC LIMIT 1
                """,
                    (guild_id, current_owner_id),
                )
                row = await cursor.fetchone()

                if not row:
                    return VoiceChannelResult(success=False, error="NO_CHANNEL")

                voice_channel_id, jtc_channel_id = row

                # Check if new owner is in the channel
                channel = discord.utils.get(
                    new_owner.guild.voice_channels, id=voice_channel_id
                )
                if not channel or new_owner not in channel.members:
                    return VoiceChannelResult(
                        success=False,
                        error="NOT_IN_CHANNEL",
                    )

                # Use the comprehensive transfer method from voice_repo
                from helpers.voice_repo import transfer_channel_owner

                success = await transfer_channel_owner(
                    voice_channel_id=voice_channel_id,
                    new_owner_id=new_owner_id,
                    guild_id=guild_id,
                    jtc_channel_id=jtc_channel_id,
                )

                if not success:
                    return VoiceChannelResult(
                        success=False,
                        error="DB_TEMP_ERROR",
                    )

                # Update permission overwrites using permissions helper
                from helpers.permissions_helper import update_channel_owner

                # Cast for type-checker: allow voice or stage channels. Still allow mocks by duck typing.
                if isinstance(
                    channel, (discord.VoiceChannel, discord.StageChannel)
                ) or (hasattr(channel, "edit") and hasattr(channel, "mention")):
                    channel_for_perms = cast(
                        "discord.VoiceChannel | discord.StageChannel", channel
                    )
                    await update_channel_owner(
                        channel=channel_for_perms,
                        new_owner_id=new_owner_id,
                        previous_owner_id=current_owner_id,
                        guild_id=guild_id,
                        jtc_channel_id=jtc_channel_id,
                    )

            return VoiceChannelResult(
                success=True,
                channel_id=voice_channel_id,
                channel_mention=channel.mention,
            )

        except Exception as e:
            self.logger.exception(
                "Error transferring voice channel ownership", exc_info=e
            )
            return VoiceChannelResult(success=False, error="UNKNOWN")

    async def get_all_voice_channels(self, guild_id: int) -> list[dict[str, Any]]:
        """
        Get all managed voice channels for a guild from voice_channels table.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of channel information dictionaries with owner_id, voice_channel_id, created_at
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT owner_id, voice_channel_id, created_at
                    FROM voice_channels
                    WHERE guild_id = ? AND is_active = 1
                    ORDER BY created_at DESC
                """,
                    (guild_id,),
                )
                rows = await cursor.fetchall()

                channels = [
                    {
                        "owner_id": row[0],
                        "voice_channel_id": row[1],
                        "created_at": row[2],
                    }
                    for row in rows
                ]

                # Filter by in-memory cache to ensure channels are still active
                # Fall back to database if cache is not available/reliable
                if self.managed_voice_channels:
                    active_channels = [
                        channel
                        for channel in channels
                        if channel["voice_channel_id"] in self.managed_voice_channels
                    ]
                    # If cache filtering results in significantly fewer channels,
                    # use database as authoritative source and update cache
                    if len(active_channels) < len(channels) * 0.5:
                        self.logger.info(
                            f"Cache appears stale, using database as source of truth for {guild_id}"
                        )
                        # Refresh cache from database
                        for channel in channels:
                            self.managed_voice_channels.add(channel["voice_channel_id"])
                        return channels
                    return active_channels
                else:
                    # No cache available, use database as source of truth
                    self.logger.info(
                        f"No cache available, using database as source of truth for {guild_id}"
                    )
                    for channel in channels:
                        self.managed_voice_channels.add(channel["voice_channel_id"])
                    return channels

        except Exception as e:
            self.logger.exception("Error getting all voice channels", exc_info=e)
            return []

    async def _validate_jtc_permissions(
        self, category: discord.CategoryChannel
    ) -> tuple[bool, str | None]:
        """
        Validate bot has permissions to create channels in a category.

        Args:
            category: Discord category channel

        Returns:
            Tuple of (can_create, error_message)
        """
        try:
            if category is None:
                return False, "Category does not exist"

            if not self.bot or not self.bot.user:
                return False, "Bot instance or bot user not available"

            guild = category.guild
            bot_member = guild.get_member(self.bot.user.id)
            if bot_member is None:
                return False, "Bot member not found in guild"

            perms = category.permissions_for(bot_member)
            if not perms.manage_channels:
                return (
                    False,
                    f"Bot missing 'Manage Channels' permission in category '{category.name}'",
                )

            return True, None

        except Exception as e:
            self.logger.exception("Error validating JTC permissions", exc_info=e)
            return False, str(e)

    async def create_jtc_channel(
        self, guild_id: int, category: discord.CategoryChannel, channel_name: str
    ) -> tuple[discord.VoiceChannel | None, str | None]:
        """
        Create a single JTC channel in a category.

        Shared method used by both setup and add commands.

        Args:
            guild_id: Discord guild ID
            category: Category to create channel in
            channel_name: Name for the new channel

        Returns:
            Tuple of (created_channel, error_message). If successful, error_message is None.
        """
        try:
            # Validate permissions first
            can_create, error = await self._validate_jtc_permissions(category)
            if not can_create:
                return None, error

            # Create the channel
            jtc_channel = await category.create_voice_channel(
                name=channel_name,
                reason="JTC channel creation via admin command",
            )

            self.logger.info(
                f"Created JTC channel {jtc_channel.id} ({channel_name}) in guild {guild_id}"
            )

            return jtc_channel, None

        except discord.Forbidden as e:
            error_msg = f"Permission denied creating JTC channel: {e}"
            self.logger.exception(error_msg)
            return None, error_msg
        except discord.HTTPException as e:
            error_msg = f"Discord API error creating JTC channel: {e}"
            self.logger.exception(error_msg)
            return None, error_msg
        except Exception as e:
            self.logger.exception("Error creating JTC channel", exc_info=e)
            return None, str(e)

    async def add_jtc_channel_to_config(
        self, guild_id: int, channel_id: int
    ) -> tuple[bool, str | None]:
        """
        Add a JTC channel to guild configuration.

        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to add

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check for duplicates
            existing_jtc = await self.config_service.get_guild_jtc_channels(guild_id)
            if channel_id in existing_jtc:
                return False, f"Channel {channel_id} is already configured as JTC"

            # Add to config
            await self.config_service.add_guild_jtc_channel(guild_id, channel_id)

            self.logger.info(
                f"Added JTC channel {channel_id} to guild {guild_id} config"
            )
            return True, None

        except Exception as e:
            self.logger.exception("Error adding JTC channel to config", exc_info=e)
            return False, str(e)

    async def remove_jtc_channel_from_config(
        self, guild_id: int, channel_id: int, cleanup_managed: bool = True
    ) -> dict[str, Any]:
        """
        Remove a JTC channel from guild configuration and clean up associated data.

        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to remove
            cleanup_managed: Whether to cleanup managed channels belonging to this JTC

        Returns:
            Dict with results:
            - success: bool
            - error: str | None
            - managed_cleanup: dict from cleanup_stale_jtc_managed_channels
            - db_purge: dict from Database.purge_stale_jtc_data
        """
        result = {
            "success": False,
            "error": None,
            "managed_cleanup": {},
            "db_purge": {},
        }

        try:
            # Check if channel is configured
            existing_jtc = await self.config_service.get_guild_jtc_channels(guild_id)
            if channel_id not in existing_jtc:
                result["error"] = f"Channel {channel_id} is not configured as JTC"
                return result

            # Remove from config
            await self.config_service.remove_guild_jtc_channel(guild_id, channel_id)
            self.logger.info(
                f"Removed JTC channel {channel_id} from guild {guild_id} config"
            )

            # Clean up managed channels if requested
            if cleanup_managed:
                result[
                    "managed_cleanup"
                ] = await self.cleanup_stale_jtc_managed_channels(
                    guild_id, {channel_id}
                )

            # Purge database records
            from services.db.database import Database

            result["db_purge"] = await Database.purge_stale_jtc_data(
                guild_id, {channel_id}
            )

            self.logger.info(
                f"JTC channel {channel_id} removal complete for guild {guild_id}: "
                f"managed_cleanup={result['managed_cleanup']}, db_purge={result['db_purge']}"
            )

            result["success"] = True
            return result

        except Exception as e:
            self.logger.exception("Error removing JTC channel from config", exc_info=e)
            result["error"] = str(e)
            return result

    async def setup_voice_system(
        self, guild_id: int, category: discord.CategoryChannel, num_channels: int = 1
    ) -> VoiceChannelResult:
        """
        Set up the voice channel system for a guild with stale JTC data cleanup.

        Args:
            guild_id: Discord guild ID
            category: Category to create channels in
            num_channels: Number of JTC channels to create

        Returns:
            VoiceChannelResult with success status
        """
        try:
            from services.db.database import Database

            # Step 1: Get old JTC channels before making changes
            old_jtc_channels = await self.config_service.get_guild_jtc_channels(
                guild_id
            )
            self.logger.info(
                f"Current JTC channels for guild {guild_id}: {old_jtc_channels}"
            )

            # Step 2: Create new JTC channels
            created_channels = []
            for i in range(num_channels):
                channel_name = (
                    f"Join to Create {i + 1}" if num_channels > 1 else "Join to Create"
                )

                # Create the voice channel (inherit permissions from parent category)
                jtc_channel = await category.create_voice_channel(
                    name=channel_name,
                    reason="Voice system setup",
                )

                created_channels.append(jtc_channel.id)
                self.logger.info(
                    f"Created JTC channel {jtc_channel.id} ({channel_name})"
                )

            # Step 3: Compute stale JTC IDs (old ones not in new ones)
            new_jtc_set = set(created_channels)
            old_jtc_set = set(old_jtc_channels) if old_jtc_channels else set()
            stale_jtc_ids = old_jtc_set - new_jtc_set

            self.logger.info(f"New JTC channels: {new_jtc_set}")
            self.logger.info(f"Stale JTC channels to clean up: {stale_jtc_ids}")

            # Step 4: Purge stale JTC data if any
            purge_stats = {}
            cleanup_stats = {}
            if stale_jtc_ids:
                # Clean up managed channels first (before database purge)
                cleanup_stats = await self.cleanup_stale_jtc_managed_channels(
                    guild_id, stale_jtc_ids
                )

                # Purge database records
                purge_stats = await Database.purge_stale_jtc_data(
                    guild_id, stale_jtc_ids
                )

                self.logger.info(
                    "Stale JTC cleanup completed - Purged: %s, Channels: %s",
                    purge_stats,
                    cleanup_stats,
                )

            # Step 5: Update guild configuration with new JTC channels
            # Replace all JTC channels with the new ones
            await self.config_service.set_guild_setting(
                guild_id, "voice.jtc_channels", created_channels
            )

            # Save voice category
            await self.config_service.set_guild_setting(
                guild_id, "voice_category_id", category.id
            )

            # Step 6: Log summary
            total_purged_rows = sum(purge_stats.values()) if purge_stats else 0
            deleted_channels_count = (
                len(cleanup_stats.get("deleted_channels", [])) if cleanup_stats else 0
            )
            failed_channels_count = (
                len(cleanup_stats.get("failed_channels", [])) if cleanup_stats else 0
            )

            self.logger.info(
                "Voice system setup complete for guild %s: Created %d JTC channels, Removed %d stale JTC IDs, "
                "Purged %d database rows, Deleted %d empty channels, Failed to delete %d channels",
                guild_id,
                len(created_channels),
                len(stale_jtc_ids),
                total_purged_rows,
                deleted_channels_count,
                failed_channels_count,
            )

            return VoiceChannelResult(success=True)

        except Exception as e:
            self.logger.exception("Error setting up voice system", exc_info=e)
            return VoiceChannelResult(success=False, error="UNKNOWN")

    async def delete_user_owned_channel(
        self, guild_id: int, user_id: int
    ) -> dict[str, Any]:
        """
        Delete user's owned voice channel and remove it from cache.

        Args:
            guild_id: Discord guild ID
            user_id: User ID whose channel to delete

        Returns:
            Dict with success status and deleted channel info
        """
        result = {
            "success": False,
            "channel_deleted": False,
            "channel_id": None,
            "error": None,
        }

        try:
            # Find the user's active voice channel
            channel_info = await self.get_user_voice_channel_info(guild_id, user_id)

            if not channel_info:
                result["success"] = True  # No channel to delete is considered success
                return result

            channel_id = channel_info.channel_id
            result["channel_id"] = channel_id

            # Try to get the actual Discord channel and delete it
            if self.bot:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    try:
                        await channel.delete(reason=f"Admin reset for user {user_id}")
                        result["channel_deleted"] = True
                        self.logger.info(
                            f"Deleted voice channel {channel_id} for user {user_id} in guild {guild_id}"
                        )
                    except (discord.NotFound, discord.Forbidden) as e:
                        self.logger.warning(
                            f"Could not delete channel {channel_id}: {e}"
                        )
                        # Continue - we'll clean up database records anyway
                else:
                    self.logger.warning(f"Channel {channel_id} not found in bot cache")

            # Remove from managed channels cache
            if channel_id in self.managed_voice_channels:
                self.managed_voice_channels.discard(channel_id)

            result["success"] = True

        except Exception as e:
            self.logger.exception("Error deleting user owned channel", exc_info=e)
            result["error"] = str(e)

        return result

    async def get_all_guild_managed_channels(self, guild_id: int) -> list[int]:
        """
        Get all managed voice channels for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of voice channel IDs
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT voice_channel_id FROM voice_channels WHERE guild_id = ? AND is_active = 1",
                    (guild_id,),
                )
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

        except Exception as e:
            self.logger.exception("Error getting guild managed channels", exc_info=e)
            return []

    async def purge_voice_data_with_cache_clear(
        self, guild_id: int, user_id: int | None = None
    ) -> dict[str, int]:
        """
        Purge voice data from database and clear relevant caches.

        Args:
            guild_id: Discord guild ID
            user_id: If provided, purge only this user's data. If None, purge all users in guild.

        Returns:
            Dict mapping table names to number of rows deleted.
        """
        from services.db.database import Database

        # Get managed channels before purging if doing guild-wide clear
        if user_id is None:
            managed_channels = await self.get_all_guild_managed_channels(guild_id)
        else:
            # For single user, get their channel info
            managed_channels = []
            channel_info = await self.get_user_voice_channel_info(guild_id, user_id)
            if channel_info:
                managed_channels = [channel_info.channel_id]

        # Purge database records
        deleted_counts = await Database.purge_voice_data(guild_id, user_id)

        # Clear cache entries for affected channels
        for channel_id in managed_channels:
            self.managed_voice_channels.discard(channel_id)

        self.logger.info(
            f"Purged voice data and cleared cache for guild {guild_id}, user {user_id}: "
            f"database={deleted_counts}, cache_cleared={len(managed_channels)} channels"
        )

        return deleted_counts

    async def cleanup_stale_jtc_managed_channels(
        self, guild_id: int, stale_jtc_ids: set[int]
    ) -> dict[str, Any]:
        """
        Find and safely delete empty managed channels belonging to stale JTC channels.

        Args:
            guild_id: Discord guild ID
            stale_jtc_ids: Set of stale JTC channel IDs

        Returns:
            Dict with cleanup statistics and any errors
        """
        if not stale_jtc_ids:
            return {"deleted_channels": [], "failed_channels": [], "errors": []}

        from services.db.database import Database

        deleted_channels = []
        failed_channels = []
        errors = []

        try:
            # Find managed channels that belong to stale JTC IDs
            stale_jtc_list = [int(x) for x in stale_jtc_ids]  # defensive cast

            # Short-circuit if no stale JTC channels to avoid IN () syntax
            if not stale_jtc_list:
                return {"deleted_channels": [], "failed_channels": [], "errors": []}

            # Build parameterized query to avoid SQL injection
            placeholders = ",".join("?" * len(stale_jtc_list))
            query = f"""
                SELECT voice_channel_id, jtc_channel_id
                FROM voice_channels
                WHERE guild_id = ? AND jtc_channel_id IN ({placeholders}) AND is_active = 1
            """

            async with Database.get_connection() as db:
                cursor = await db.execute(
                    query,
                    [guild_id, *stale_jtc_list],
                )
                stale_managed_channels = await cursor.fetchall()

            # Attempt to delete each managed channel if it's empty
            if self.bot:
                for voice_channel_id, jtc_channel_id in stale_managed_channels:
                    try:
                        channel = self.bot.get_channel(voice_channel_id)
                        if channel and isinstance(channel, discord.VoiceChannel):
                            # Only delete if channel is empty or has only bot members
                            non_bot_members = [
                                m
                                for m in channel.members
                                if isinstance(m, discord.Member) and m.bot
                            ]
                            if len(non_bot_members) == 0:
                                await channel.delete(
                                    reason=f"Cleanup stale JTC {jtc_channel_id} managed channel"
                                )
                                deleted_channels.append(
                                    {
                                        "voice_channel_id": voice_channel_id,
                                        "jtc_channel_id": jtc_channel_id,
                                    }
                                )
                                # Remove from cache
                                self.managed_voice_channels.discard(voice_channel_id)
                                self.logger.info(
                                    f"Deleted empty managed channel {voice_channel_id} for stale JTC {jtc_channel_id}"
                                )
                            else:
                                # Channel has users, don't delete but log
                                self.logger.warning(
                                    f"Skipping deletion of managed channel {voice_channel_id} - has {len(non_bot_members)} non-bot members"
                                )
                                failed_channels.append(
                                    {
                                        "voice_channel_id": voice_channel_id,
                                        "jtc_channel_id": jtc_channel_id,
                                        "reason": "has_users",
                                    }
                                )
                        elif channel:
                            # Channel exists but we can't check members (shouldn't happen for voice channels)
                            self.logger.warning(
                                f"Cannot check member count for channel {voice_channel_id}, skipping deletion"
                            )
                            failed_channels.append(
                                {
                                    "voice_channel_id": voice_channel_id,
                                    "jtc_channel_id": jtc_channel_id,
                                    "reason": "cannot_check_members",
                                }
                            )
                        else:
                            # Channel doesn't exist in bot cache, remove from our tracking anyway
                            self.managed_voice_channels.discard(voice_channel_id)
                            self.logger.info(
                                f"Managed channel {voice_channel_id} not found, removed from cache"
                            )

                    except (discord.NotFound, discord.Forbidden) as e:
                        # Channel already gone or no permissions, that's fine
                        self.logger.info(
                            f"Could not delete managed channel {voice_channel_id}: {e}"
                        )
                        self.managed_voice_channels.discard(voice_channel_id)
                    except Exception as e:
                        error_msg = (
                            f"Error deleting managed channel {voice_channel_id}: {e}"
                        )
                        self.logger.exception(error_msg)
                        errors.append(error_msg)
                        failed_channels.append(
                            {
                                "voice_channel_id": voice_channel_id,
                                "jtc_channel_id": jtc_channel_id,
                                "reason": "exception",
                                "error": str(e),
                            }
                        )

        except Exception as e:
            error_msg = f"Error during stale JTC cleanup: {e}"
            self.logger.exception(error_msg)
            errors.append(error_msg)

        result = {
            "deleted_channels": deleted_channels,
            "failed_channels": failed_channels,
            "errors": errors,
        }

        self.logger.info(
            f"Stale JTC cleanup for guild {guild_id}: "
            f"deleted={len(deleted_channels)}, failed={len(failed_channels)}, errors={len(errors)}"
        )

        return result

    async def create_admin_settings_embed(
        self,
        guild_id: int,
        user_id: int,
        user: discord.Member,
        settings: dict[str, Any],
    ) -> discord.Embed:
        """
        Create an admin view of a user's voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            user: Discord member object
            settings: Settings dictionary

        Returns:
            Discord embed with formatted admin view
        """
        embed = discord.Embed(
            title=f"🔧 Voice Settings for {user.display_name}",
            description=f"Administrative view of voice channel settings for {user.mention}",
            color=discord.Color.orange(),
        )

        if not settings:
            embed.add_field(
                name="Settings", value="No custom settings found.", inline=False
            )
        else:
            settings_text = []
            for key, value in settings.items():
                formatted_key = key.replace("_", " ").title()
                settings_text.append(f"**{formatted_key}:** {value}")

            embed.add_field(
                name="Current Settings", value="\n".join(settings_text), inline=False
            )

        # Add user info
        embed.add_field(
            name="User Info",
            value=f"**ID:** {user_id}\n**Mention:** {user.mention}",
            inline=True,
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        return embed
