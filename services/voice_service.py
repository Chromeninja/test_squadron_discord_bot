"""
Voice service for managing voice channels and related functionality.
"""

import asyncio
import contextlib
import sqlite3
import time
from collections.abc import Coroutine, Iterable
from typing import Any, ClassVar, cast

import discord

# Re-exported for test patching (tests patch services.voice_service.enforce_permission_changes)
from helpers.voice_permissions import enforce_permission_changes  # noqa: F401
from services.db.database import Database
from services.db.repository import BaseRepository
from services.voice_channel_helpers import (
    classify_old_channel,
    sanitize_overwrite,
)
from services.voice_channel_helpers import get_member_count as resolve_member_count
from services.voice_channel_mixin import VoiceChannelMixin
from services.voice_create_mixin import VoiceCreateMixin
from services.voice_jtc_mixin import VoiceJtcMixin
from services.voice_reconcile_mixin import VoiceReconcileMixin
from services.voice_settings_mixin import VoiceSettingsMixin
from services.voice_setup_mixin import VoiceSetupMixin
from services.voice_state_mixin import VoiceStateMixin

from .base import BaseService
from .config_service import ConfigService


# Function alias for test patching - avoids circular import
async def update_last_used_jtc_channel(guild_id: int, user_id: int, jtc_channel_id: int) -> None:
    """Alias for test patching to avoid circular imports."""
    from helpers.voice_settings import update_last_used_jtc_channel as real_func

    await real_func(guild_id, user_id, jtc_channel_id)


class VoiceService(
    VoiceChannelMixin,
    VoiceSettingsMixin,
    VoiceStateMixin,
    VoiceCreateMixin,
    VoiceReconcileMixin,
    VoiceJtcMixin,
    VoiceSetupMixin,
    BaseService,
):
    """
    Service for managing voice channels in a race-safe, predictable manner.

    Handles voice channel creation, deletion, cooldowns, and settings
    with proper async safety and deduplication.
    """

    # Owner ID used to mark channels as orphaned (no owner)
    ORPHAN_OWNER_ID = 0
    # Seconds to keep users marked as creating (prevents duplicate events)
    CREATION_UNMARK_DELAY_SECONDS = 2.0
    # Seconds before stale creation locks are cleaned up
    LOCK_CLEANUP_AGE_SECONDS = 300
    # Seconds to wait for Discord API during channel creation
    CHANNEL_CREATION_TIMEOUT_SECONDS = 10.0
    # Days before inactive voice channels are purged (7 days)
    INACTIVE_CHANNEL_PURGE_DAYS = 7
    # Critical bot permissions that must be present on a newly created channel
    # to avoid lockout while still inheriting JTC/category permissions.
    #
    # `manage_roles` is intentionally omitted. Discord requires the bot to already
    # have category/guild-level Manage Permissions during channel creation, and a
    # channel overwrite cannot bootstrap that capability if the category denies it.
    BOT_CREATION_OVERWRITE_PERMISSIONS: ClassVar[dict[str, bool]] = {
        "view_channel": True,
        "manage_channels": True,
        "connect": True,
        "move_members": True,
    }
    OWNER_CREATION_OVERWRITE_PERMISSIONS: ClassVar[dict[str, bool]] = {
        "connect": True
    }

    def __init__(
        self,
        config_service: ConfigService,
        bot: "discord.Client | None" = None,
        test_mode: bool = False,
        auto_start_background: bool = False,
    ) -> None:
        super().__init__("voice")
        self.config_service = config_service
        self.bot = bot  # Store bot instance for channel operations
        self.test_mode = test_mode
        # Explicit opt-in for starting background tasks during initialize().
        # Defaults to False to avoid event loop leaks in tests/CI.
        self.auto_start_background = auto_start_background
        self._background_tasks: set[asyncio.Task] = set()
        # Track creation locks (tagged keys) and when they were last used for cleanup
        # Keys are prefixed tuples so user-scoped locks cannot collide with JTC locks
        self._creation_locks: dict[tuple[str, int, int], asyncio.Lock] = {}
        self._lock_last_used: dict[tuple[str, int, int], float] = {}
        self._locks_lock = asyncio.Lock()
        self._creation_unmark_delay = self.CREATION_UNMARK_DELAY_SECONDS

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

    async def _ensure_voice_tables(self) -> None:
        """No-op placeholder retained for tests that still call this hook."""
        return None

    def _spawn_background_task(
        self, coro: Coroutine[Any, Any, Any], *, name: str
    ) -> asyncio.Task:
        """Create and track a background task with exception logging."""

        task = asyncio.create_task(coro, name=name)

        # Test harnesses may monkeypatch asyncio.create_task to return a non-Task stub.
        # Cast to Any first so mypy doesn't see the isinstance check as unreachable.
        task_any: Any = task
        if not isinstance(task_any, asyncio.Task):
            with contextlib.suppress(Exception):
                coro.close()
            return task_any  # type: ignore[return-value]
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

        # Only start background tasks if explicitly enabled and not in test mode
        if self.auto_start_background and not self.test_mode:
            self._spawn_background_task(self._cleanup_task(), name="voice.cleanup_task")
            self._spawn_background_task(
                self._run_reconcile_after_ready(),
                name="voice.reconcile_after_ready",
            )

    async def start_background_tasks(self) -> None:
        """Explicitly start long-running background tasks.

        Call this from application startup when you want the service to run
        its maintenance and reconciliation loops. Tests should avoid calling
        this unless they intend to exercise background behaviors.
        """
        if self.test_mode:
            return
        # Prevent duplicate scheduling
        existing_names = {
            t.get_name() for t in self._background_tasks if isinstance(t, asyncio.Task)
        }
        if "voice.cleanup_task" not in existing_names:
            self._spawn_background_task(self._cleanup_task(), name="voice.cleanup_task")
        if "voice.reconcile_after_ready" not in existing_names:
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

        # Cancel and await all background tasks (snapshot once to avoid race condition)
        tasks_to_cancel = list(self._background_tasks)
        for task in tasks_to_cancel:
            task.cancel()

        if tasks_to_cancel:
            # Await all tasks that were marked for cancellation
            gathered_results = await asyncio.gather(
                *tasks_to_cancel, return_exceptions=True
            )
            for i, result in enumerate(gathered_results):
                if isinstance(result, Exception) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    task = tasks_to_cancel[i]
                    self.logger.warning(
                        "Background task %s raised during shutdown: %s",
                        task.get_name(),
                        result,
                    )

        self._background_tasks.clear()

    async def _load_managed_channels(self) -> None:
        """Load existing managed channels from database. Do not delete DB rows if channel is not in cache; defer to reconciliation."""
        try:
            # Get startup cleanup mode setting
            startup_cleanup_mode = await self.config_service.get_global_setting(
                "voice.startup_cleanup_mode", "delayed"
            )

            async with BaseRepository.transaction() as db:
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

        except sqlite3.OperationalError as exc:
            self.logger.warning(
                "Voice tables unavailable while loading managed channels: %s", exc
            )
        except Exception as exc:
            self.logger.exception("Error loading managed channels", exc_info=exc)

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

    async def _cleanup_stale_locks(self, max_age_seconds: int | None = None) -> None:
        """Remove lock objects that have not been used recently."""
        if max_age_seconds is None:
            max_age_seconds = self.LOCK_CLEANUP_AGE_SECONDS
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

    def _get_member_count(
        self,
        channel_or_id: discord.VoiceChannel | discord.StageChannel | int | None,
    ) -> int:
        """Return the member count for a voice-like channel using cache fallback."""
        return resolve_member_count(
            channel_or_id,
            bot=self.bot,
            voice_channel_members=self._voice_channel_members,
            logger=self.logger,
        )

    def _classify_old_channel(
        self,
        member_count: int,
    ) -> str:
        """Classify what to do with an existing channel when a new one is created."""
        return classify_old_channel(member_count)

    @staticmethod
    def _sanitize_overwrite(
        overwrite: discord.PermissionOverwrite,
        bot_perms: discord.Permissions,
    ) -> discord.PermissionOverwrite:
        """Remove allowed permission bits the bot itself lacks."""
        return sanitize_overwrite(overwrite, bot_perms)

    async def _delete_channel_safe(
        self,
        channel_or_id: discord.VoiceChannel | discord.StageChannel | int,
        reason: str = "Channel cleanup",
        *,
        cleanup_tracking: bool = True,
    ) -> bool:
        """
        Safely delete a voice channel, handling NotFound/Forbidden gracefully.

        Args:
            channel_or_id: The channel object or channel ID to delete
            reason: Audit log reason for deletion
            cleanup_tracking: Whether to remove from managed_voice_channels cache

        Returns:
            True if channel was deleted or already gone, False if deletion failed
        """
        channel: discord.VoiceChannel | discord.StageChannel | None = None
        channel_id: int

        if isinstance(channel_or_id, int):
            channel_id = channel_or_id
            if self.bot:
                ch = self.bot.get_channel(channel_id)
                if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                    channel = ch
        else:
            channel = channel_or_id
            channel_id = channel.id

        try:
            if channel is not None:
                await channel.delete(reason=reason)
                self.logger.info(f"Deleted voice channel {channel_id}: {reason}")
            else:
                self.logger.debug(
                    f"Channel {channel_id} not in cache, skipping Discord deletion"
                )
        except discord.NotFound:
            # Channel already deleted - this is fine
            self.logger.debug(f"Channel {channel_id} already deleted")
        except discord.Forbidden as e:
            self.logger.warning(
                f"Insufficient permissions to delete channel {channel_id}: {e}"
            )
            return False
        except Exception as e:
            self.logger.exception(
                f"Unexpected error deleting channel {channel_id}", exc_info=e
            )
            return False
        finally:
            if cleanup_tracking:
                self.managed_voice_channels.discard(channel_id)

        return True

    async def _handle_orphan_or_delete(
        self,
        *,
        db: Any,
        action: str,
        user_id: int,
        old_channel_id: int,
        old_channel: discord.VoiceChannel | discord.StageChannel | None,
    ) -> discord.VoiceChannel | None:
        """Perform orphaning or deletion for an old channel and return orphaned channel if applicable."""

        if action == "orphan":
            try:
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
            except sqlite3.OperationalError:
                # Backward compatibility for schemas without previous_owner_id
                await db.execute(
                    """
                    UPDATE voice_channels
                    SET owner_id = ?, last_activity = ?, is_active = 1
                    WHERE voice_channel_id = ?
                    """,
                    (
                        self.ORPHAN_OWNER_ID,
                        int(time.time()),
                        old_channel_id,
                    ),
                )

            if isinstance(old_channel, discord.VoiceChannel):
                return old_channel
            if hasattr(old_channel, "edit") and hasattr(old_channel, "overwrites"):
                return cast("discord.VoiceChannel", old_channel)
            return None

        # Default delete path
        await db.execute(
            "DELETE FROM voice_channel_settings WHERE voice_channel_id = ?",
            (old_channel_id,),
        )
        await db.execute(
            "DELETE FROM voice_channels WHERE voice_channel_id = ?",
            (old_channel_id,),
        )

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

