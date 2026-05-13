"""
Metrics Service

Collects and aggregates user activity metrics: voice time, game sessions,
and message counts. Uses in-memory buffers with periodic flush to a
separate metrics SQLite database to minimize write contention.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.base import BaseService
from services.db.metrics_db import MetricsDatabase
from services.metrics_activity import tier_from_cadence

# Re-export _hour_bucket so existing test imports (from services.metrics_service import _hour_bucket) still work
from services.metrics_buckets import hour_bucket as _hour_bucket  # noqa: F401
from services.metrics_buckets import message_window_bucket as _message_window_bucket
from services.metrics_flush import MetricsFlushMixin
from services.metrics_models import GameSessionInfo, MetricsSnapshot, VoiceSessionInfo
from services.metrics_read import MetricsReadMixin

if TYPE_CHECKING:
    from discord.ext.commands import Bot

    from services.config_service import ConfigService


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MetricsService(MetricsReadMixin, MetricsFlushMixin, BaseService):
    """
    Collects voice, game, and message metrics with in-memory buffering.

    Architecture:
        - Events call record_*() methods which update in-memory state
        - A periodic flush task writes buffered message counts to the DB
        - A periodic rollup task pre-aggregates hourly data
        - A periodic purge task removes data older than retention_days

    The service owns its own MetricsDatabase connection (separate SQLite file).
    """

    @staticmethod
    def _tier_from_cadence(
        active_days: set[int],
        range_start_day: int,
        range_days: int,
    ) -> str:
        """Derive activity tier from cadence-window coverage over a day range."""
        return tier_from_cadence(active_days, range_start_day, range_days)

    def __init__(
        self,
        config_service: ConfigService,
        bot: Bot | None = None,
        *,
        test_mode: bool = False,
    ) -> None:
        super().__init__("metrics")
        self._config_service = config_service
        self._bot = bot
        self._test_mode = test_mode

        # Configuration (populated in _initialize_impl)
        self._retention_days: int = 90
        self._rollup_interval: int = 3600  # seconds
        self._flush_interval: int = 30  # seconds
        self._enabled: bool = True
        self._db_path: str = "metrics.db"

        # In-memory state
        # Active voice sessions keyed by (guild_id, user_id)
        self._voice_sessions: dict[tuple[int, int], VoiceSessionInfo] = {}
        # Active game sessions keyed by (guild_id, user_id)
        self._game_sessions: dict[tuple[int, int], GameSessionInfo] = {}
        # Buffered message counts: (guild_id, user_id, message_bucket) -> count
        self._message_buffer: defaultdict[tuple[int, int, int], int] = defaultdict(int)
        self._message_buffer_lock = asyncio.Lock()

        # Background task handles
        self._flush_task: asyncio.Task | None = None
        self._rollup_task: asyncio.Task | None = None
        self._purge_task: asyncio.Task | None = None

        # Stats for health_check
        self._last_flush_at: float = 0
        self._last_rollup_at: float = 0
        self._total_messages_buffered: int = 0

        # Guild-level metrics channel exclusions cache
        self._excluded_channels_cache: dict[int, tuple[float, set[int]]] = {}
        self._excluded_channels_ttl_seconds: int = 30
        self._excluded_channels_lock = asyncio.Lock()

        # Guild-level tracked games config cache
        self._tracked_games_cache: dict[int, tuple[float, str, set[str]]] = {}
        self._tracked_games_ttl_seconds: int = 30
        self._tracked_games_lock = asyncio.Lock()

        # Guild-level activity threshold cache
        # {guild_id: (monotonic_ts, min_voice_secs, min_game_secs, min_messages)}
        self._activity_thresholds_cache: dict[int, tuple[float, int, int, int]] = {}
        self._activity_thresholds_ttl_seconds: int = 30
        self._activity_thresholds_lock = asyncio.Lock()

        # Activity group counts cache: {(guild_id, days, user_filter): (ts, counts)}
        self._activity_group_counts_cache: dict[
            tuple[int, int, tuple[int, ...] | None],
            tuple[float, dict[str, dict[str, int]]],
        ] = {}
        self._activity_group_counts_ttl_seconds: int = 15
        self._activity_group_counts_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _initialize_impl(self) -> None:
        """Initialize the metrics DB and start background tasks."""
        # Read config — metrics is a top-level section in config.yaml
        metrics_cfg = await self._config_service.get_global_setting("metrics", {}) or {}
        self._enabled = metrics_cfg.get("enabled", True)
        if not self._enabled:
            self.logger.info("Metrics collection is disabled via config")
            return

        self._retention_days = metrics_cfg.get("retention_days", 90)
        self._rollup_interval = metrics_cfg.get("rollup_interval_minutes", 60) * 60
        self._flush_interval = metrics_cfg.get("buffer_flush_seconds", 30)
        self._db_path = metrics_cfg.get("database_path", "metrics.db")

        # Resolve relative path against project root
        if not Path(self._db_path).is_absolute():
            project_root = Path(__file__).resolve().parent.parent
            self._db_path = str(project_root / self._db_path)

        # Initialize the separate metrics database
        await MetricsDatabase.initialize(self._db_path)

        # Start background tasks (skip in test mode)
        if not self._test_mode:
            self._flush_task = asyncio.create_task(
                self._flush_loop(), name="metrics_flush"
            )
            self._rollup_task = asyncio.create_task(
                self._rollup_loop(), name="metrics_rollup"
            )
            self._purge_task = asyncio.create_task(
                self._purge_loop(), name="metrics_purge"
            )

        self.logger.info(
            "MetricsService initialized (db=%s, retention=%dd, flush=%ds)",
            self._db_path,
            self._retention_days,
            self._flush_interval,
        )

    async def _shutdown_impl(self) -> None:
        """Flush buffers, close open sessions, cancel tasks."""
        # Cancel background tasks
        for task in (self._flush_task, self._rollup_task, self._purge_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    continue

        if not self._enabled:
            return

        # Flush remaining message buffer
        await self._flush_message_buffer()

        # Close all open voice sessions
        now = int(time.time())
        for key in list(self._voice_sessions):
            session = self._voice_sessions.pop(key)
            await self._write_voice_session_end(session, now)

        # Close all open game sessions
        for key in list(self._game_sessions):
            game_session = self._game_sessions.pop(key)
            await self._write_game_session_end(game_session, now)

        self.logger.info("MetricsService shut down — all sessions closed")

    # ------------------------------------------------------------------
    # Public recording API
    # ------------------------------------------------------------------

    def record_message(
        self, guild_id: int, user_id: int, channel_id: int | None = None
    ) -> None:
        """
        Record a message event (non-async for minimal overhead).

        Increments the in-memory buffer; flushed to DB periodically.

        channel_id is accepted for caller compatibility and future use.
        """
        if not self._enabled:
            return
        message_bucket = _message_window_bucket(int(time.time()))
        self._message_buffer[(guild_id, user_id, message_bucket)] += 1
        self._total_messages_buffered += 1

    async def record_voice_join(
        self, guild_id: int, user_id: int, channel_id: int
    ) -> None:
        """Record a user joining a voice channel."""
        if not self._enabled:
            return
        key = (guild_id, user_id)
        # Close any existing session first (e.g., channel switch)
        if key in self._voice_sessions:
            await self.record_voice_leave(guild_id, user_id)

        self._voice_sessions[key] = VoiceSessionInfo(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            joined_at=int(time.time()),
        )

    async def record_voice_leave(self, guild_id: int, user_id: int) -> None:
        """Record a user leaving a voice channel."""
        if not self._enabled:
            return
        key = (guild_id, user_id)
        session = self._voice_sessions.pop(key, None)
        if session:
            await self._write_voice_session_end(session, int(time.time()))

    async def record_game_start(
        self, guild_id: int, user_id: int, game_name: str
    ) -> None:
        """Record a user starting a game."""
        if not self._enabled:
            return
        key = (guild_id, user_id)
        # Close any existing game session first
        if key in self._game_sessions:
            await self.record_game_stop(guild_id, user_id)

        self._game_sessions[key] = GameSessionInfo(
            guild_id=guild_id,
            user_id=user_id,
            game_name=game_name,
            started_at=int(time.time()),
        )

    async def record_game_stop(self, guild_id: int, user_id: int) -> None:
        """Record a user stopping a game."""
        if not self._enabled:
            return
        key = (guild_id, user_id)
        session = self._game_sessions.pop(key, None)
        if session:
            await self._write_game_session_end(session, int(time.time()))

    # ------------------------------------------------------------------
    # Live snapshot (for dashboard "now" view)
    # ------------------------------------------------------------------

    def get_live_snapshot(self, guild_id: int) -> MetricsSnapshot:
        """Return a point-in-time snapshot of live metrics for a guild."""
        now = int(time.time())
        today_start = now - (now % 86400)  # midnight UTC

        # Messages today from buffer
        messages_today = sum(
            count
            for (gid, _uid, bucket), count in self._message_buffer.items()
            if gid == guild_id and bucket >= today_start
        )

        # Active voice users
        active_voice = sum(1 for (gid, _) in self._voice_sessions if gid == guild_id)

        # Active game sessions + top game
        game_counts: defaultdict[str, int] = defaultdict(int)
        active_game_sessions = 0
        for (gid, _), session in self._game_sessions.items():
            if gid == guild_id:
                active_game_sessions += 1
                game_counts[session.game_name] += 1

        top_game = (
            max(game_counts, key=lambda game_name: game_counts[game_name])
            if game_counts
            else None
        )

        return MetricsSnapshot(
            messages_today=messages_today,
            active_voice_users=active_voice,
            active_game_sessions=active_game_sessions,
            top_game=top_game,
        )

    async def backfill_voice_state(self, bot: Bot) -> None:
        """
        Scan all guilds for users currently in voice channels and open sessions.

        Called on bot startup / on_ready to recover state.  Only members who
        are **not** self-muted and **not** self-deafened are considered eligible
        for an active voice session.

        Excluded channels are honoured identically to the live event handler
        so that backfill never collects data the operator has opted out of.
        """
        if not self._enabled:
            return

        count = 0
        for guild in bot.guilds:
            excluded_ids = await self.get_excluded_channel_ids(guild.id)
            for vc in guild.voice_channels:
                if vc.id in excluded_ids:
                    continue
                for member in vc.members:
                    if member.bot:
                        continue
                    # Skip members who are self-muted or self-deafened
                    voice = member.voice
                    if voice is not None and (voice.self_mute or voice.self_deaf):
                        continue
                    key = (guild.id, member.id)
                    if key not in self._voice_sessions:
                        self._voice_sessions[key] = VoiceSessionInfo(
                            guild_id=guild.id,
                            user_id=member.id,
                            channel_id=vc.id,
                            joined_at=int(time.time()),
                        )
                        count += 1

        if count:
            self.logger.info(
                "Backfilled %d active voice sessions from current state", count
            )

    async def backfill_game_state(self, bot: Bot) -> None:
        """
        Scan all guilds for members currently playing games and open sessions.

        Requires the presences intent.

        Members sitting in an excluded voice channel are skipped, matching
        the live ``on_presence_update`` handler's minimization behaviour.
        """
        if not self._enabled:
            return

        import discord

        count = 0
        for guild in bot.guilds:
            excluded_ids = await self.get_excluded_channel_ids(guild.id)
            for member in guild.members:
                if member.bot:
                    continue
                # Skip members in excluded voice channels (mirrors live handler)
                voice_state = getattr(member, "voice", None)
                current_vc_id = (
                    voice_state.channel.id
                    if voice_state is not None and voice_state.channel is not None
                    else None
                )
                if current_vc_id in excluded_ids:
                    continue
                for activity in member.activities:
                    if (
                        activity.type == discord.ActivityType.playing
                        and hasattr(activity, "name")
                        and activity.name
                    ):
                        key = (guild.id, member.id)
                        if key not in self._game_sessions:
                            self._game_sessions[key] = GameSessionInfo(
                                guild_id=guild.id,
                                user_id=member.id,
                                game_name=activity.name,
                                started_at=int(time.time()),
                            )
                            count += 1
                        break  # Only track first game per user

        if count:
            self.logger.info(
                "Backfilled %d active game sessions from current state", count
            )

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def delete_user_metrics(self, guild_id: int, user_id: int) -> dict[str, int]:
        """
        Delete all metrics data for a specific user in a guild.

        Returns a dict mapping table name -> number of rows deleted.
        Used to honour data-deletion / right-to-erasure requests.
        """
        self._ensure_initialized()
        deleted: dict[str, int] = {}

        # Also purge the in-memory buffers for this user
        async with self._message_buffer_lock:
            keys_to_remove = [
                k for k in self._message_buffer if k[0] == guild_id and k[1] == user_id
            ]
            for k in keys_to_remove:
                del self._message_buffer[k]

        self._voice_sessions.pop((guild_id, user_id), None)
        self._game_sessions.pop((guild_id, user_id), None)

        try:
            async with MetricsDatabase.get_connection() as db:
                for table in (
                    "voice_sessions",
                    "game_sessions",
                    "message_counts",
                    "metrics_user_hourly",
                ):
                    cursor = await db.execute(
                        f"DELETE FROM {table} WHERE guild_id = ? AND user_id = ?",
                        (guild_id, user_id),
                    )
                    deleted[table] = cursor.rowcount
                await db.commit()
        except Exception:
            self.logger.exception(
                "Failed to delete metrics for user %d in guild %d",
                user_id,
                guild_id,
            )
            raise

        self.logger.info(
            "Deleted metrics for user %d in guild %d: %s",
            user_id,
            guild_id,
            deleted,
        )
        return deleted

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return health status including buffer sizes and task state."""
        base = await super().health_check()
        base.update(
            {
                "enabled": self._enabled,
                "active_voice_sessions": len(self._voice_sessions),
                "active_game_sessions": len(self._game_sessions),
                "message_buffer_size": sum(self._message_buffer.values()),
                "last_flush_at": self._last_flush_at,
                "last_rollup_at": self._last_rollup_at,
                "total_messages_buffered": self._total_messages_buffered,
            }
        )
        return base
