"""
Metrics Service

Collects and aggregates user activity metrics: voice time, game sessions,
and message counts. Uses in-memory buffers with periodic flush to a
separate metrics SQLite database to minimize write contention.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.base import BaseService
from services.db.metrics_db import MetricsDatabase

if TYPE_CHECKING:
    from discord.ext.commands import Bot

    from services.config_service import ConfigService


# ---------------------------------------------------------------------------
# Data classes for in-memory session tracking
# ---------------------------------------------------------------------------

@dataclass
class VoiceSessionInfo:
    """Tracks an active voice session for a user."""

    guild_id: int
    user_id: int
    channel_id: int
    joined_at: int  # Unix epoch seconds


@dataclass
class GameSessionInfo:
    """Tracks an active game session for a user."""

    guild_id: int
    user_id: int
    game_name: str
    started_at: int  # Unix epoch seconds


@dataclass
class MetricsSnapshot:
    """Point-in-time snapshot of live metrics for a guild."""

    messages_today: int = 0
    active_voice_users: int = 0
    active_game_sessions: int = 0
    top_game: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MetricsService(BaseService):
    """
    Collects voice, game, and message metrics with in-memory buffering.

    Architecture:
        - Events call record_*() methods which update in-memory state
        - A periodic flush task writes buffered message counts to the DB
        - A periodic rollup task pre-aggregates hourly data
        - A periodic purge task removes data older than retention_days

    The service owns its own MetricsDatabase connection (separate SQLite file).
    """

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
        # Buffered message counts: (guild_id, user_id, hour_bucket) -> count
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
            self._flush_task = asyncio.create_task(self._flush_loop(), name="metrics_flush")
            self._rollup_task = asyncio.create_task(self._rollup_loop(), name="metrics_rollup")
            self._purge_task = asyncio.create_task(self._purge_loop(), name="metrics_purge")

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
                    pass

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
            session = self._game_sessions.pop(key)
            await self._write_game_session_end(session, now)

        self.logger.info("MetricsService shut down — all sessions closed")

    # ------------------------------------------------------------------
    # Public recording API
    # ------------------------------------------------------------------

    async def get_excluded_channel_ids(
        self, guild_id: int, *, force_refresh: bool = False
    ) -> set[int]:
        """Return excluded channel IDs for metrics collection in this guild."""
        now = time.monotonic()

        async with self._excluded_channels_lock:
            cached = self._excluded_channels_cache.get(guild_id)
            if (
                not force_refresh
                and cached is not None
                and (now - cached[0]) < self._excluded_channels_ttl_seconds
            ):
                return set(cached[1])

        raw_value = await self._config_service.get_guild_setting(
            guild_id,
            "metrics.excluded_channel_ids",
            [],
        )

        parsed: set[int] = set()
        if isinstance(raw_value, list):
            for item in raw_value:
                try:
                    parsed.add(int(item))
                except (TypeError, ValueError):
                    continue

        async with self._excluded_channels_lock:
            self._excluded_channels_cache[guild_id] = (time.monotonic(), parsed)

        return set(parsed)

    def record_message(self, guild_id: int, user_id: int, channel_id: int | None = None) -> None:
        """
        Record a message event (non-async for minimal overhead).

        Increments the in-memory buffer; flushed to DB periodically.

        channel_id is accepted for caller compatibility and future use.
        """
        if not self._enabled:
            return
        hour_bucket = _hour_bucket(int(time.time()))
        self._message_buffer[(guild_id, user_id, hour_bucket)] += 1
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
        active_voice = sum(
            1 for (gid, _) in self._voice_sessions if gid == guild_id
        )

        # Active game sessions + top game
        game_counts: defaultdict[str, int] = defaultdict(int)
        for (gid, _), session in self._game_sessions.items():
            if gid == guild_id:
                game_counts[session.game_name] += 1

        top_game = max(game_counts, key=game_counts.get, default=None) if game_counts else None  # type: ignore[arg-type]

        return MetricsSnapshot(
            messages_today=messages_today,
            active_voice_users=active_voice,
            active_game_sessions=len(game_counts),
            top_game=top_game,
        )

    # ------------------------------------------------------------------
    # Query methods (for API endpoints)
    # ------------------------------------------------------------------

    async def get_guild_metrics(
        self, guild_id: int, days: int = 7
    ) -> dict[str, Any]:
        """
        Get aggregated metrics for a guild over the given period.

        Returns:
            Dict with total_messages, avg_messages_per_user, total_voice_seconds,
            avg_voice_per_user, unique_users, top_games.
        """
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)
        cutoff_hour = _hour_bucket(cutoff)

        async with MetricsDatabase.get_connection() as db:
            # Message totals
            cursor = await db.execute(
                "SELECT COALESCE(SUM(message_count), 0), COUNT(DISTINCT user_id) "
                "FROM message_counts WHERE guild_id = ? AND hour_bucket >= ?",
                (guild_id, cutoff_hour),
            )
            row = await cursor.fetchone()
            total_messages = row[0] if row else 0
            unique_messagers = row[1] if row else 0

            # Voice totals
            cursor = await db.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0), COUNT(DISTINCT user_id) "
                "FROM voice_sessions "
                "WHERE guild_id = ? AND left_at IS NOT NULL AND left_at >= ?",
                (guild_id, cutoff),
            )
            row = await cursor.fetchone()
            total_voice_seconds = row[0] if row else 0
            unique_voice_users = row[1] if row else 0

            # Unique users count across all tracked activity sources
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM ("
                "SELECT user_id FROM message_counts WHERE guild_id = ? AND hour_bucket >= ? "
                "UNION "
                "SELECT user_id FROM voice_sessions WHERE guild_id = ? AND left_at IS NOT NULL AND left_at >= ? "
                "UNION "
                "SELECT user_id FROM game_sessions WHERE guild_id = ? AND ended_at IS NOT NULL AND ended_at >= ?"
                ")",
                (guild_id, cutoff_hour, guild_id, cutoff, guild_id, cutoff),
            )
            row = await cursor.fetchone()
            unique_users = row[0] if row else 1  # avoid div-by-zero

            # Top games
            cursor = await db.execute(
                "SELECT game_name, SUM(duration_seconds) as total_time, "
                "COUNT(*) as session_count, "
                "AVG(duration_seconds) as avg_time "
                "FROM game_sessions "
                "WHERE guild_id = ? AND ended_at IS NOT NULL AND ended_at >= ? AND duration_seconds IS NOT NULL "
                "GROUP BY game_name ORDER BY total_time DESC LIMIT 10",
                (guild_id, cutoff),
            )
            top_games = [
                {
                    "game_name": r[0],
                    "total_seconds": r[1],
                    "session_count": r[2],
                    "avg_seconds": round(r[3]) if r[3] else 0,
                }
                for r in await cursor.fetchall()
            ]

        avg_messages = round(total_messages / max(unique_users, 1), 1)
        avg_voice = round(total_voice_seconds / max(unique_users, 1))

        return {
            "total_messages": total_messages,
            "unique_messagers": unique_messagers,
            "avg_messages_per_user": avg_messages,
            "total_voice_seconds": total_voice_seconds,
            "unique_voice_users": unique_voice_users,
            "avg_voice_per_user": avg_voice,
            "unique_users": unique_users,
            "top_games": top_games,
        }

    async def get_voice_leaderboard(
        self, guild_id: int, days: int = 7, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top users by voice time."""
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT user_id, SUM(duration_seconds) as total "
                "FROM voice_sessions "
                "WHERE guild_id = ? AND left_at IS NOT NULL AND left_at >= ? AND duration_seconds > 0 "
                "GROUP BY user_id ORDER BY total DESC LIMIT ?",
                (guild_id, cutoff, limit),
            )
            return [
                {"user_id": r[0], "total_seconds": r[1]}
                for r in await cursor.fetchall()
            ]

    async def get_message_leaderboard(
        self, guild_id: int, days: int = 7, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top users by message count."""
        self._ensure_initialized()
        cutoff_hour = _hour_bucket(int(time.time()) - (days * 86400))

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT user_id, SUM(message_count) as total "
                "FROM message_counts "
                "WHERE guild_id = ? AND hour_bucket >= ? AND message_count > 0 "
                "GROUP BY user_id ORDER BY total DESC LIMIT ?",
                (guild_id, cutoff_hour, limit),
            )
            return [
                {"user_id": r[0], "total_messages": r[1]}
                for r in await cursor.fetchall()
            ]

    async def get_timeseries(
        self, guild_id: int, metric: str = "messages", days: int = 7
    ) -> list[dict[str, Any]]:
        """
        Get hourly time-series data for a guild.

        Args:
            metric: One of "messages", "voice", "games"
        """
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)
        cutoff_hour = _hour_bucket(cutoff)

        async with MetricsDatabase.get_connection() as db:
            if metric == "messages":
                cursor = await db.execute(
                    "SELECT hour_bucket, SUM(message_count), COUNT(DISTINCT user_id) "
                    "FROM message_counts WHERE guild_id = ? AND hour_bucket >= ? "
                    "GROUP BY hour_bucket "
                    "ORDER BY hour_bucket",
                    (guild_id, cutoff_hour),
                )
                return [
                    {"timestamp": r[0], "value": r[1], "unique_users": r[2]}
                    for r in await cursor.fetchall()
                ]
            elif metric == "voice":
                cursor = await db.execute(
                    "SELECT (left_at - (left_at % 3600)) as hour_bucket, "
                    "SUM(duration_seconds), COUNT(DISTINCT user_id) "
                    "FROM voice_sessions "
                    "WHERE guild_id = ? AND left_at IS NOT NULL AND left_at >= ? "
                    "AND duration_seconds IS NOT NULL "
                    "GROUP BY hour_bucket "
                    "ORDER BY hour_bucket",
                    (guild_id, cutoff),
                )
                return [
                    {"timestamp": r[0], "value": r[1], "unique_users": r[2]}
                    for r in await cursor.fetchall()
                ]
            elif metric == "games":
                cursor = await db.execute(
                    "SELECT (ended_at - (ended_at % 3600)) as hour_bucket, game_name, SUM(duration_seconds) as total "
                    "FROM game_sessions "
                    "WHERE guild_id = ? AND ended_at IS NOT NULL AND ended_at >= ? AND duration_seconds IS NOT NULL "
                    "GROUP BY hour_bucket, game_name "
                    "ORDER BY hour_bucket, total DESC",
                    (guild_id, cutoff),
                )
                bucket_top_game: dict[int, str] = {}
                for hour_bucket, game_name, _total in await cursor.fetchall():
                    if hour_bucket not in bucket_top_game:
                        bucket_top_game[hour_bucket] = game_name
                return [
                    {"timestamp": hour_bucket, "top_game": game_name}
                    for hour_bucket, game_name in sorted(bucket_top_game.items())
                ]
            else:
                return []

    async def get_top_games(
        self, guild_id: int, days: int = 7, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top games by total play time."""
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT game_name, SUM(duration_seconds) as total_time, "
                "COUNT(*) as session_count, "
                "AVG(duration_seconds) as avg_time, "
                "COUNT(DISTINCT user_id) as unique_players "
                "FROM game_sessions "
                "WHERE guild_id = ? AND started_at >= ? AND duration_seconds IS NOT NULL "
                "GROUP BY game_name ORDER BY total_time DESC LIMIT ?",
                (guild_id, cutoff, limit),
            )
            return [
                {
                    "game_name": r[0],
                    "total_seconds": r[1],
                    "session_count": r[2],
                    "avg_seconds": round(r[3]) if r[3] else 0,
                    "unique_players": r[4],
                }
                for r in await cursor.fetchall()
            ]

    async def get_user_metrics(
        self, guild_id: int, user_id: int, days: int = 7
    ) -> dict[str, Any]:
        """Get detailed metrics for a specific user."""
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)
        cutoff_hour = _hour_bucket(cutoff)

        async with MetricsDatabase.get_connection() as db:
            # Aggregate totals
            cursor = await db.execute(
                "SELECT COALESCE(SUM(message_count), 0) "
                "FROM message_counts "
                "WHERE guild_id = ? AND user_id = ? AND hour_bucket >= ?",
                (guild_id, user_id, cutoff_hour),
            )
            row = await cursor.fetchone()
            total_messages = row[0] if row else 0

            cursor = await db.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0) "
                "FROM voice_sessions "
                "WHERE guild_id = ? AND user_id = ? AND left_at IS NOT NULL AND left_at >= ?",
                (guild_id, user_id, cutoff),
            )
            row = await cursor.fetchone()
            total_voice_seconds = row[0] if row else 0

            # Time series for this user
            cursor = await db.execute(
                "SELECT hour_bucket, SUM(message_count) "
                "FROM message_counts "
                "WHERE guild_id = ? AND user_id = ? AND hour_bucket >= ? "
                "GROUP BY hour_bucket "
                "ORDER BY hour_bucket",
                (guild_id, user_id, cutoff_hour),
            )
            msg_by_hour: dict[int, int] = {r[0]: r[1] for r in await cursor.fetchall()}

            cursor = await db.execute(
                "SELECT (left_at - (left_at % 3600)) as hour_bucket, SUM(duration_seconds) "
                "FROM voice_sessions "
                "WHERE guild_id = ? AND user_id = ? AND left_at IS NOT NULL AND left_at >= ? "
                "AND duration_seconds IS NOT NULL "
                "GROUP BY hour_bucket "
                "ORDER BY hour_bucket",
                (guild_id, user_id, cutoff),
            )
            voice_by_hour: dict[int, int] = {r[0]: r[1] for r in await cursor.fetchall()}

            all_hours = sorted(set(msg_by_hour) | set(voice_by_hour))
            timeseries = [
                {
                    "timestamp": hour_bucket,
                    "messages": msg_by_hour.get(hour_bucket, 0),
                    "voice_seconds": voice_by_hour.get(hour_bucket, 0),
                }
                for hour_bucket in all_hours
            ]

            # Top games for this user
            cursor = await db.execute(
                "SELECT game_name, SUM(duration_seconds) as total_seconds "
                "FROM game_sessions "
                "WHERE guild_id = ? AND user_id = ? AND ended_at IS NOT NULL AND ended_at >= ? "
                "AND duration_seconds IS NOT NULL "
                "GROUP BY game_name "
                "ORDER BY total_seconds DESC "
                "LIMIT 10",
                (guild_id, user_id, cutoff),
            )
            top_games = [
                {"game_name": r[0], "total_seconds": r[1]}
                for r in await cursor.fetchall()
            ]

            avg_messages_per_day = round(total_messages / max(days, 1), 1)
            avg_voice_per_day = round(total_voice_seconds / max(days, 1))

        return {
            "user_id": user_id,
            "total_messages": total_messages,
            "total_voice_seconds": total_voice_seconds,
            "avg_messages_per_day": avg_messages_per_day,
            "avg_voice_per_day": avg_voice_per_day,
            "top_games": top_games,
            "timeseries": timeseries,
        }

    # ------------------------------------------------------------------
    # Backfill (on bot ready)
    # ------------------------------------------------------------------

    async def backfill_voice_state(self, bot: Bot) -> None:
        """
        Scan all guilds for users currently in voice channels and open sessions.

        Called on bot startup / on_ready to recover state.
        """
        if not self._enabled:
            return

        count = 0
        for guild in bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
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
            self.logger.info("Backfilled %d active voice sessions from current state", count)

    async def backfill_game_state(self, bot: Bot) -> None:
        """
        Scan all guilds for members currently playing games and open sessions.

        Requires the presences intent.
        """
        if not self._enabled:
            return

        import discord

        count = 0
        for guild in bot.guilds:
            for member in guild.members:
                if member.bot:
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
            self.logger.info("Backfilled %d active game sessions from current state", count)

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Periodically flush the message buffer to the database."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_message_buffer()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Error in metrics flush loop")
                await asyncio.sleep(5)

    async def _rollup_loop(self) -> None:
        """Periodically aggregate raw data into hourly rollups."""
        while True:
            try:
                await asyncio.sleep(self._rollup_interval)
                await self._perform_rollup()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Error in metrics rollup loop")
                await asyncio.sleep(60)

    async def _purge_loop(self) -> None:
        """Purge old metrics data once per day."""
        while True:
            try:
                await asyncio.sleep(86400)  # Run once per day
                await self._purge_old_data()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Error in metrics purge loop")
                await asyncio.sleep(3600)

    # ------------------------------------------------------------------
    # Internal write helpers
    # ------------------------------------------------------------------

    async def _write_voice_session_end(
        self, session: VoiceSessionInfo, ended_at: int
    ) -> None:
        """Write a completed voice session to the database."""
        duration = max(0, ended_at - session.joined_at)
        try:
            async with MetricsDatabase.get_connection() as db:
                await db.execute(
                    "INSERT INTO voice_sessions (guild_id, user_id, channel_id, joined_at, left_at, duration_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session.guild_id,
                        session.user_id,
                        session.channel_id,
                        session.joined_at,
                        ended_at,
                        duration,
                    ),
                )
                await db.commit()
        except Exception:
            self.logger.exception(
                "Failed to write voice session for user %d in guild %d",
                session.user_id,
                session.guild_id,
            )

    async def _write_game_session_end(
        self, session: GameSessionInfo, ended_at: int
    ) -> None:
        """Write a completed game session to the database."""
        duration = max(0, ended_at - session.started_at)
        try:
            async with MetricsDatabase.get_connection() as db:
                await db.execute(
                    "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session.guild_id,
                        session.user_id,
                        session.game_name,
                        session.started_at,
                        ended_at,
                        duration,
                    ),
                )
                await db.commit()
        except Exception:
            self.logger.exception(
                "Failed to write game session for user %d in guild %d",
                session.user_id,
                session.guild_id,
            )

    async def _flush_message_buffer(self) -> None:
        """Write buffered message counts to the database via upsert."""
        async with self._message_buffer_lock:
            if not self._message_buffer:
                return
            # Snapshot and clear
            snapshot = dict(self._message_buffer)
            self._message_buffer.clear()

        try:
            async with MetricsDatabase.get_connection() as db:
                for (guild_id, user_id, hour_bucket), count in snapshot.items():
                    await db.execute(
                        "INSERT INTO message_counts (guild_id, user_id, hour_bucket, message_count) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(guild_id, user_id, hour_bucket) "
                        "DO UPDATE SET message_count = message_count + excluded.message_count",
                        (guild_id, user_id, hour_bucket, count),
                    )
                await db.commit()
            self._last_flush_at = time.time()
        except Exception:
            self.logger.exception("Failed to flush message buffer")
            # Re-add unflushed data
            async with self._message_buffer_lock:
                for key, count in snapshot.items():
                    self._message_buffer[key] += count

    async def _perform_rollup(self) -> None:
        """
        Aggregate raw data from the last rollup period into hourly rollup tables.

        Covers the previous hour's worth of data.
        """
        now = int(time.time())
        hour_start = _hour_bucket(now) - 3600  # Previous completed hour
        hour_end = hour_start + 3600

        try:
            async with MetricsDatabase.get_connection() as db:
                # ---------- Server-wide hourly rollup ----------
                # Messages
                cursor = await db.execute(
                    "SELECT guild_id, SUM(message_count), COUNT(DISTINCT user_id) "
                    "FROM message_counts "
                    "WHERE hour_bucket >= ? AND hour_bucket < ? "
                    "GROUP BY guild_id",
                    (hour_start, hour_end),
                )
                msg_rows = await cursor.fetchall()

                # Voice
                cursor = await db.execute(
                    "SELECT guild_id, SUM(duration_seconds), COUNT(DISTINCT user_id) "
                    "FROM voice_sessions "
                    "WHERE joined_at < ? AND (left_at >= ? OR left_at IS NULL) "
                    "AND duration_seconds IS NOT NULL "
                    "GROUP BY guild_id",
                    (hour_end, hour_start),
                )
                voice_rows = {r[0]: (r[1], r[2]) for r in await cursor.fetchall()}

                # Top game per guild
                cursor = await db.execute(
                    "SELECT guild_id, game_name, SUM(duration_seconds) as total "
                    "FROM game_sessions "
                    "WHERE started_at < ? AND (ended_at >= ? OR ended_at IS NULL) "
                    "AND duration_seconds IS NOT NULL "
                    "GROUP BY guild_id, game_name "
                    "ORDER BY total DESC",
                    (hour_end, hour_start),
                )
                top_games: dict[int, str] = {}
                for r in await cursor.fetchall():
                    if r[0] not in top_games:
                        top_games[r[0]] = r[1]

                # Upsert server-wide
                guild_ids = set()
                for r in msg_rows:
                    guild_ids.add(r[0])
                guild_ids.update(voice_rows.keys())
                guild_ids.update(top_games.keys())

                for gid in guild_ids:
                    msg_data = next((r for r in msg_rows if r[0] == gid), None)
                    total_msgs = msg_data[1] if msg_data else 0
                    unique_msgs = msg_data[2] if msg_data else 0
                    v_secs, v_users = voice_rows.get(gid, (0, 0))
                    top_game = top_games.get(gid)

                    await db.execute(
                        "INSERT INTO metrics_hourly "
                        "(guild_id, hour_bucket, total_messages, unique_messagers, "
                        "total_voice_seconds, unique_voice_users, top_game) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(guild_id, hour_bucket) DO UPDATE SET "
                        "total_messages = excluded.total_messages, "
                        "unique_messagers = excluded.unique_messagers, "
                        "total_voice_seconds = excluded.total_voice_seconds, "
                        "unique_voice_users = excluded.unique_voice_users, "
                        "top_game = excluded.top_game",
                        (gid, hour_start, total_msgs, unique_msgs, v_secs, v_users, top_game),
                    )

                # ---------- Per-user hourly rollup ----------
                # Messages per user
                cursor = await db.execute(
                    "SELECT guild_id, user_id, SUM(message_count) "
                    "FROM message_counts "
                    "WHERE hour_bucket >= ? AND hour_bucket < ? "
                    "GROUP BY guild_id, user_id",
                    (hour_start, hour_end),
                )
                user_msg_rows = await cursor.fetchall()

                # Voice per user
                cursor = await db.execute(
                    "SELECT guild_id, user_id, SUM(duration_seconds) "
                    "FROM voice_sessions "
                    "WHERE joined_at < ? AND (left_at >= ? OR left_at IS NULL) "
                    "AND duration_seconds IS NOT NULL "
                    "GROUP BY guild_id, user_id",
                    (hour_end, hour_start),
                )
                user_voice: dict[tuple[int, int], int] = {
                    (r[0], r[1]): r[2] for r in await cursor.fetchall()
                }

                # Games per user (as JSON)
                cursor = await db.execute(
                    "SELECT guild_id, user_id, game_name, SUM(duration_seconds) "
                    "FROM game_sessions "
                    "WHERE started_at < ? AND (ended_at >= ? OR ended_at IS NULL) "
                    "AND duration_seconds IS NOT NULL "
                    "GROUP BY guild_id, user_id, game_name",
                    (hour_end, hour_start),
                )
                user_games: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
                for r in await cursor.fetchall():
                    user_games[(r[0], r[1])][r[2]] = r[3]

                # Collect all user keys
                user_keys: set[tuple[int, int]] = set()
                for r in user_msg_rows:
                    user_keys.add((r[0], r[1]))
                user_keys.update(user_voice.keys())
                user_keys.update(user_games.keys())

                for gid, uid in user_keys:
                    msgs = next((r[2] for r in user_msg_rows if r[0] == gid and r[1] == uid), 0)
                    voice_secs = user_voice.get((gid, uid), 0)
                    games_dict = user_games.get((gid, uid))
                    games_json = json.dumps(games_dict) if games_dict else None

                    await db.execute(
                        "INSERT INTO metrics_user_hourly "
                        "(guild_id, user_id, hour_bucket, messages_sent, voice_seconds, games_json) "
                        "VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(guild_id, user_id, hour_bucket) DO UPDATE SET "
                        "messages_sent = excluded.messages_sent, "
                        "voice_seconds = excluded.voice_seconds, "
                        "games_json = excluded.games_json",
                        (gid, uid, hour_start, msgs, voice_secs, games_json),
                    )

                await db.commit()

            self._last_rollup_at = time.time()
            self.logger.debug("Hourly rollup completed for bucket %d", hour_start)

        except Exception:
            self.logger.exception("Failed to perform hourly rollup")

    async def _purge_old_data(self) -> None:
        """Delete metrics data older than retention_days."""
        cutoff = int(time.time()) - (self._retention_days * 86400)

        try:
            async with MetricsDatabase.get_connection() as db:
                for table, col in [
                    ("voice_sessions", "joined_at"),
                    ("game_sessions", "started_at"),
                    ("message_counts", "hour_bucket"),
                    ("metrics_hourly", "hour_bucket"),
                    ("metrics_user_hourly", "hour_bucket"),
                ]:
                    cursor = await db.execute(
                        f"DELETE FROM {table} WHERE {col} < ?", (cutoff,)
                    )
                    deleted = cursor.rowcount
                    if deleted:
                        self.logger.info(
                            "Purged %d rows from %s (older than %d days)",
                            deleted, table, self._retention_days,
                        )
                await db.commit()
        except Exception:
            self.logger.exception("Failed to purge old metrics data")

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return health status including buffer sizes and task state."""
        base = await super().health_check()
        base.update({
            "enabled": self._enabled,
            "active_voice_sessions": len(self._voice_sessions),
            "active_game_sessions": len(self._game_sessions),
            "message_buffer_size": sum(self._message_buffer.values()),
            "last_flush_at": self._last_flush_at,
            "last_rollup_at": self._last_rollup_at,
            "total_messages_buffered": self._total_messages_buffered,
        })
        return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hour_bucket(epoch: int) -> int:
    """Truncate a Unix timestamp to the start of its hour."""
    return epoch - (epoch % 3600)
