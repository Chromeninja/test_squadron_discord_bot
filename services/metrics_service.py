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
from typing import TYPE_CHECKING, Any, ClassVar

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
        async with self._excluded_channels_lock:
            now = time.monotonic()
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

            self._excluded_channels_cache[guild_id] = (time.monotonic(), parsed)
            return set(parsed)

    async def get_tracked_game_config(
        self, guild_id: int, *, force_refresh: bool = False
    ) -> tuple[str, set[str]]:
        """Return (mode, game_names) for activity-group game tracking.

        mode is 'all' or 'specific'. When 'all', game_names is empty and
        every game counts. When 'specific', only games in game_names count.
        """
        async with self._tracked_games_lock:
            now = time.monotonic()
            cached = self._tracked_games_cache.get(guild_id)
            if (
                not force_refresh
                and cached is not None
                and (now - cached[0]) < self._tracked_games_ttl_seconds
            ):
                return cached[1], set(cached[2])

            mode_raw = await self._config_service.get_guild_setting(
                guild_id, "metrics.tracked_games_mode", "all"
            )
            mode = mode_raw if mode_raw in ("all", "specific") else "all"

            games_raw = await self._config_service.get_guild_setting(
                guild_id, "metrics.tracked_games", []
            )
            games: set[str] = set()
            if isinstance(games_raw, list):
                for item in games_raw:
                    name = str(item).strip()
                    if name:
                        games.add(name)

            self._tracked_games_cache[guild_id] = (time.monotonic(), mode, games)
            return mode, set(games)

    async def get_activity_thresholds(
        self, guild_id: int, *, force_refresh: bool = False
    ) -> tuple[int, int, int]:
        """Return (min_voice_seconds, min_game_seconds, min_messages) for a guild.

        Defaults: 15 min voice, 15 min game, 5 messages.
        Values are cached with 30s TTL.
        """
        # Fast-path: read cache under lock, return if valid.
        async with self._activity_thresholds_lock:
            now = time.monotonic()
            cached = self._activity_thresholds_cache.get(guild_id)
            if (
                not force_refresh
                and cached is not None
                and (now - cached[0]) < self._activity_thresholds_ttl_seconds
            ):
                return cached[1], cached[2], cached[3]

        # Fetch and parse outside the lock to reduce contention.
        raw_voice = await self._config_service.get_guild_setting(
            guild_id,
            "metrics.min_voice_minutes",
            15,
        )
        raw_game = await self._config_service.get_guild_setting(
            guild_id,
            "metrics.min_game_minutes",
            15,
        )
        raw_msgs = await self._config_service.get_guild_setting(
            guild_id,
            "metrics.min_messages",
            5,
        )
        try:
            min_voice_secs = max(0, int(raw_voice)) * 60
        except (TypeError, ValueError):
            min_voice_secs = 15 * 60
        try:
            min_game_secs = max(0, int(raw_game)) * 60
        except (TypeError, ValueError):
            min_game_secs = 15 * 60
        try:
            min_msgs = max(0, int(raw_msgs))
        except (TypeError, ValueError):
            min_msgs = 5

        # Write computed values to cache under the lock.
        async with self._activity_thresholds_lock:
            self._activity_thresholds_cache[guild_id] = (
                time.monotonic(),
                min_voice_secs,
                min_game_secs,
                min_msgs,
            )
        return min_voice_secs, min_game_secs, min_msgs

    # ------------------------------------------------------------------
    # Activity-group bucket computation
    # ------------------------------------------------------------------

    # Tier cadence: (tier_name, window_size_in_days)
    # Checked strictest-first; user gets the first tier where every
    # non-overlapping window of that size contains at least one active day.
    _TIER_CADENCE_DAYS: ClassVar[list[tuple[str, int]]] = [
        ("hardcore", 1),  # active every day
        ("regular", 3),  # active once every 3 days
        ("casual", 7),  # active once every 7 days (weekly)
        ("reserve", 30),  # active once every 30 days (monthly)
    ]

    @staticmethod
    def _tier_from_cadence(
        active_days: set[int],
        range_start_day: int,
        range_days: int,
    ) -> str:
        """Derive a tier label from cadence coverage over a time range.

        The range is divided into non-overlapping windows of each tier's
        cadence size.  The user qualifies for a tier when *every* window
        contains at least one active day.  Reserve is skipped when the
        range is shorter than 30 days.

        Example — 7-day range starting at day-bucket 20000::

            range_start_day = 20000, range_days = 7

            hardcore (window=1): 7 windows → [20000, 20001, …, 20006].
              User must have an active day in *each* 1-day window (all 7 days).

            regular  (window=3): ceil(7/3) = 3 windows →
              [20000–20003), [20003–20006), [20006–20007).
              User must have ≥1 active day in each of the 3 windows.

            casual   (window=7): ceil(7/7) = 1 window →
              [20000–20007).  Any single active day qualifies.

            reserve  (window=30): skipped (30 > 7).

        The last window may be shorter than ``window_days`` when
        ``range_days`` is not an exact multiple — it still requires at
        least one active day.

        AI Notes:
            ``active_days`` contains integer day-buckets (Unix timestamp
            ``// 86400``).  ``range_start_day`` is the first day-bucket
            in the range, which spans ``range_days`` day-buckets.
        """
        if not active_days:
            return "inactive"
        for tier_name, window_days in MetricsService._TIER_CADENCE_DAYS:
            if window_days > range_days:
                continue  # e.g., skip reserve for 7-day range
            num_windows = -(-range_days // window_days)  # ceil div
            all_covered = True
            for i in range(num_windows):
                w_start = range_start_day + i * window_days
                w_end = range_start_day + min(
                    (i + 1) * window_days,
                    range_days,
                )
                if not any(w_start <= d < w_end for d in active_days):
                    all_covered = False
                    break
            if all_covered:
                return tier_name

        return "inactive"

    async def get_member_activity_buckets(
        self,
        guild_id: int,
        user_ids: list[int] | None = None,
        lookback_days: int = 30,
        now_utc: int | None = None,
    ) -> dict[int, dict[str, Any]]:
        """Compute per-dimension activity tiers for members.

        Tiers are based on *cadence* — consistent activity coverage
        across the lookback period measured in strict non-overlapping
        windows rather than simple recency.

        Returns ``{user_id: {voice_tier, chat_tier, game_tier,
        combined_tier, last_voice_at, last_chat_at, last_game_at}}``
        """
        self._ensure_initialized()
        now = now_utc or int(time.time())
        normalized_lookback = max(1, min(lookback_days, 365))

        # Day-aligned range: last N days ending *today* (inclusive)
        now_day = now // 86400
        range_start_day = now_day - normalized_lookback + 1
        cutoff_ts = range_start_day * 86400

        excluded = await self.get_excluded_channel_ids(guild_id)
        game_mode, tracked_games = await self.get_tracked_game_config(guild_id)
        min_voice_secs, min_game_secs, min_msgs = await self.get_activity_thresholds(
            guild_id
        )
        min_msg_windows = min_msgs

        user_filter_sql = ""
        params_prefix: list[Any] = [guild_id]
        if user_ids is not None:
            if not user_ids:
                return {}
            placeholders = ",".join("?" for _ in user_ids)
            user_filter_sql = f" AND user_id IN ({placeholders})"
            params_prefix = [guild_id, *user_ids]

        async def _fetch_chat_activity() -> tuple[dict[int, set[int]], dict[int, int]]:
            """Fetch per-user active chat day buckets and last chat timestamp."""
            sql_msg = (
                "SELECT user_id, hour_bucket / 86400 AS day_bucket, "
                "SUM(message_count) AS day_message_count, MAX(hour_bucket) "
                "FROM message_counts "
                f"WHERE guild_id = ? {user_filter_sql} "
                "AND bucket_seconds = 180 "
                "AND hour_bucket >= ? "
                "GROUP BY user_id, day_bucket"
            )
            chat_days: dict[int, set[int]] = {}
            last_chat: dict[int, int] = {}
            async with MetricsDatabase.get_connection() as db:
                cursor = await db.execute(sql_msg, [*params_prefix, cutoff_ts])
                for uid, day_bucket, day_message_count, max_ts in await cursor.fetchall():
                    if day_message_count < min_msg_windows:
                        continue
                    chat_days.setdefault(uid, set()).add(day_bucket)
                    last_chat[uid] = max(last_chat.get(uid, 0), max_ts)
            return chat_days, last_chat

        async def _fetch_voice_activity() -> tuple[dict[int, set[int]], dict[int, int]]:
            """Fetch per-user active voice day buckets and last voice timestamp."""
            sql_voice = (
                "SELECT user_id, joined_at, COALESCE(left_at, ?) "
                "FROM voice_sessions "
                f"WHERE guild_id = ? {user_filter_sql} "
                "AND joined_at <= ? AND COALESCE(left_at, ?) > ? "
            )
            voice_day_secs: dict[tuple[int, int], int] = {}
            voice_last: dict[int, int] = {}
            async with MetricsDatabase.get_connection() as db:
                cursor = await db.execute(
                    sql_voice,
                    [now, *params_prefix, now, now, cutoff_ts],
                )
                for uid, joined_at, ended_at in await cursor.fetchall():
                    clamped_start = max(joined_at, cutoff_ts)
                    clamped_end = min(ended_at, now)
                    if clamped_start > clamped_end:
                        continue
                    voice_last[uid] = max(voice_last.get(uid, 0), ended_at)
                    for d in range(clamped_start // 86400, clamped_end // 86400 + 1):
                        day_start = max(clamped_start, d * 86400)
                        day_end = min(clamped_end, (d + 1) * 86400)
                        voice_day_secs[(uid, d)] = voice_day_secs.get((uid, d), 0) + max(
                            0,
                            day_end - day_start,
                        )

            voice_days: dict[int, set[int]] = {}
            for (uid, day_bucket), secs in voice_day_secs.items():
                if secs < min_voice_secs:
                    continue
                voice_days.setdefault(uid, set()).add(day_bucket)
            return voice_days, voice_last

        async def _fetch_game_activity() -> tuple[dict[int, set[int]], dict[int, int]]:
            """Fetch per-user active game day buckets and last game timestamp."""
            excl_clause = ""
            excl_params: list[Any] = []
            if excluded:
                excl_placeholders = ",".join("?" for _ in excluded)
                excl_clause = f" AND v.channel_id NOT IN ({excl_placeholders})"
                excl_params = list(excluded)

            game_name_clause = ""
            game_name_params: list[Any] = []
            if game_mode == "specific" and tracked_games:
                gn_placeholders = ",".join("?" for _ in tracked_games)
                game_name_clause = f" AND g.game_name IN ({gn_placeholders})"
                game_name_params = list(tracked_games)

            game_user_filter = ""
            game_user_params: list[Any] = []
            if user_ids is not None:
                placeholders = ",".join("?" for _ in user_ids)
                game_user_filter = f" AND g.user_id IN ({placeholders})"
                game_user_params = list(user_ids)

            sql_game = (
                "SELECT DISTINCT g.user_id, g.started_at, "
                "COALESCE(g.ended_at, ?) "
                "FROM game_sessions g "
                "JOIN voice_sessions v "
                "  ON g.guild_id = v.guild_id AND g.user_id = v.user_id "
                "  AND g.started_at < COALESCE(v.left_at, ?) "
                "  AND COALESCE(g.ended_at, ?) > v.joined_at "
                f"WHERE g.guild_id = ? "
                f"AND g.started_at <= ? AND COALESCE(g.ended_at, ?) > ?"
                f"{game_user_filter}{excl_clause}{game_name_clause}"
            )
            game_params: list[Any] = [
                now,
                now,
                now,
                guild_id,
                now,
                now,
                cutoff_ts,
                *game_user_params,
                *excl_params,
                *game_name_params,
            ]

            game_day_secs: dict[tuple[int, int], int] = {}
            game_last: dict[int, int] = {}
            async with MetricsDatabase.get_connection() as db:
                cursor = await db.execute(sql_game, game_params)
                for uid, started_at, ended_at in await cursor.fetchall():
                    clamped_start = max(started_at, cutoff_ts)
                    clamped_end = min(ended_at, now)
                    if clamped_start > clamped_end:
                        continue
                    game_last[uid] = max(game_last.get(uid, 0), ended_at)
                    for d in range(clamped_start // 86400, clamped_end // 86400 + 1):
                        day_start = max(clamped_start, d * 86400)
                        day_end = min(clamped_end, (d + 1) * 86400)
                        game_day_secs[(uid, d)] = game_day_secs.get((uid, d), 0) + max(
                            0,
                            day_end - day_start,
                        )

            game_days: dict[int, set[int]] = {}
            for (uid, day_bucket), secs in game_day_secs.items():
                if secs < min_game_secs:
                    continue
                game_days.setdefault(uid, set()).add(day_bucket)
            return game_days, game_last

        # Intermediate store: {uid: {active_<dim>_days: set, last_<dim>_at: int}}
        user_data: dict[int, dict[str, Any]] = {}

        (
            (chat_days, last_chat),
            (voice_days, last_voice),
            (game_days, last_game),
        ) = await asyncio.gather(
            _fetch_chat_activity(),
            _fetch_voice_activity(),
            _fetch_game_activity(),
        )

        for uid, days_set in chat_days.items():
            entry = user_data.setdefault(uid, {})
            entry["active_chat_days"] = days_set
            entry["last_chat_at"] = last_chat.get(uid, 0)

        for uid, days_set in voice_days.items():
            entry = user_data.setdefault(uid, {})
            entry["active_voice_days"] = days_set
            entry["last_voice_at"] = last_voice.get(uid, 0)

        for uid, days_set in game_days.items():
            entry = user_data.setdefault(uid, {})
            entry["active_game_days"] = days_set
            entry["last_game_at"] = last_game.get(uid, 0)

        # Classify tiers per dimension + combined
        result: dict[int, dict[str, Any]] = {}
        for uid, data in user_data.items():
            chat_days = data.get("active_chat_days", set())
            voice_days = data.get("active_voice_days", set())
            game_days = data.get("active_game_days", set())
            combined_days = chat_days | voice_days | game_days
            result[uid] = {
                "last_chat_at": data.get("last_chat_at"),
                "last_voice_at": data.get("last_voice_at"),
                "last_game_at": data.get("last_game_at"),
                "voice_tier": self._tier_from_cadence(
                    voice_days,
                    range_start_day,
                    normalized_lookback,
                ),
                "chat_tier": self._tier_from_cadence(
                    chat_days,
                    range_start_day,
                    normalized_lookback,
                ),
                "game_tier": self._tier_from_cadence(
                    game_days,
                    range_start_day,
                    normalized_lookback,
                ),
                "combined_tier": self._tier_from_cadence(
                    combined_days,
                    range_start_day,
                    normalized_lookback,
                ),
            }

        return result

    async def get_activity_group_counts(
        self,
        guild_id: int,
        user_ids: list[int] | None = None,
        days: int = 30,
    ) -> dict[str, dict[str, int]]:
        """Return tier counts per dimension for the Metrics page chips.

        Returns: {
            "voice": {"hardcore": N, "regular": N, ...},
            "chat": {...}, "game": {...}, "combined": {...}
        }
        """
        normalized_days = max(1, min(days, 365))
        user_filter_key = tuple(sorted(user_ids)) if user_ids is not None else None
        cache_key = (guild_id, normalized_days, user_filter_key)
        async with self._activity_group_counts_lock:
            cached = self._activity_group_counts_cache.get(cache_key)
            if cached is not None:
                cached_ts, cached_counts = cached
                if (
                    time.monotonic() - cached_ts
                    < self._activity_group_counts_ttl_seconds
                ):
                    return {
                        dim: dict(tier_counts)
                        for dim, tier_counts in cached_counts.items()
                    }

        buckets = await self.get_member_activity_buckets(
            guild_id,
            user_ids=user_ids,
            lookback_days=normalized_days,
        )
        dimensions = ("voice", "chat", "game", "combined")
        tier_names = ("hardcore", "regular", "casual", "reserve", "inactive")
        counts: dict[str, dict[str, int]] = {
            dim: dict.fromkeys(tier_names, 0) for dim in dimensions
        }
        for _uid, data in buckets.items():
            for dim in dimensions:
                tier = data.get(f"{dim}_tier", "inactive")
                counts[dim][tier] = counts[dim].get(tier, 0) + 1

        async with self._activity_group_counts_lock:
            self._activity_group_counts_cache[cache_key] = (
                time.monotonic(),
                {dim: dict(tier_counts) for dim, tier_counts in counts.items()},
            )

        return counts

    def _invalidate_activity_group_counts_cache(
        self,
        guild_id: int | None = None,
    ) -> None:
        """Invalidate cached activity group counts globally or for one guild."""
        if guild_id is None:
            self._activity_group_counts_cache.clear()
            return

        keys_to_delete = [
            key for key in self._activity_group_counts_cache if key[0] == guild_id
        ]
        for key in keys_to_delete:
            self._activity_group_counts_cache.pop(key, None)

    async def get_activity_group_user_ids(
        self,
        guild_id: int,
        dimension: str,
        tier: str,
        lookback_days: int = 30,
    ) -> list[int]:
        """Return user IDs matching a specific dimension+tier combo."""
        buckets = await self.get_member_activity_buckets(
            guild_id,
            lookback_days=lookback_days,
        )
        key = f"{dimension}_tier"
        return [uid for uid, data in buckets.items() if data.get(key) == tier]

    async def get_activity_group_user_ids_bulk(
        self,
        guild_id: int,
        dimensions: list[str],
        tiers: list[str],
        lookback_days: int = 30,
    ) -> dict[str, dict[str, list[int]]]:
        """Return user IDs for multiple dimension+tier combos in one call.

        Returns a nested mapping of ``{dimension: {tier: [user_id, ...]}}``.
        Only requested dimension/tier pairs are included.

        AI Notes:
            This avoids O(dimensions × tiers) separate HTTP round-trips when
            the web backend resolves activity filters.  A single call to
            ``get_member_activity_buckets`` is shared across all combos.
        """
        buckets = await self.get_member_activity_buckets(
            guild_id,
            lookback_days=lookback_days,
        )
        result: dict[str, dict[str, list[int]]] = {}
        for dim in dimensions:
            key = f"{dim}_tier"
            tier_map: dict[str, list[int]] = {}
            for t in tiers:
                tier_map[t] = [
                    uid for uid, data in buckets.items() if data.get(key) == t
                ]
            result[dim] = tier_map
        return result

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

    async def get_messages_today(self, guild_id: int) -> int:
        """Return today's message total (UTC) from DB plus current in-memory buffer.

        AI Notes:
            The dashboard "Live" row should represent current day totals, not
            only unflushed in-memory increments.  We combine persisted rows from
            ``message_counts`` with the current buffer to avoid dropping to zero
            between flushes or after process restarts.
        """
        self._ensure_initialized()

        now = int(time.time())
        today_start = now - (now % 86400)  # midnight UTC

        # Capture current in-memory increments for today.
        async with self._message_buffer_lock:
            buffered_today = sum(
                count
                for (gid, _uid, bucket), count in self._message_buffer.items()
                if gid == guild_id and bucket >= today_start
            )

        persisted_today = 0
        try:
            async with MetricsDatabase.get_connection() as db:
                cursor = await db.execute(
                    "SELECT COALESCE(SUM(message_count), 0) "
                    "FROM message_counts "
                    "WHERE guild_id = ? AND hour_bucket >= ?",
                    (guild_id, today_start),
                )
                row = await cursor.fetchone()
                persisted_today = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            self.logger.exception(
                "Failed to query persisted messages_today for guild %d",
                guild_id,
            )

        return persisted_today + buffered_today

    # ------------------------------------------------------------------
    # Query methods (for API endpoints)
    # ------------------------------------------------------------------

    async def get_guild_metrics(
        self, guild_id: int, days: int = 7, user_ids: list[int] | None = None
    ) -> dict[str, Any]:
        """
        Get aggregated metrics for a guild over the given period.

        When user_ids is provided, only those users' data is included.
        """
        self._ensure_initialized()
        cutoff_hour = _hour_bucket(int(time.time()) - (days * 86400))

        uid_filter = ""
        uid_params: list[Any] = []
        if user_ids is not None:
            if not user_ids:
                return {
                    "total_messages": 0,
                    "unique_messagers": 0,
                    "avg_messages_per_user": 0.0,
                    "total_voice_seconds": 0,
                    "unique_voice_users": 0,
                    "avg_voice_per_user": 0,
                    "unique_users": 0,
                    "top_games": [],
                }
            placeholders = ",".join("?" for _ in user_ids)
            uid_filter = f" AND user_id IN ({placeholders})"
            uid_params = list(user_ids)

        async with MetricsDatabase.get_connection() as db:
            if user_ids is not None:
                # Filtered path: use per-user hourly rollups
                cursor = await db.execute(
                    "SELECT "
                    "COALESCE(SUM(messages_sent), 0), "
                    "COUNT(DISTINCT CASE WHEN messages_sent > 0 THEN user_id END), "
                    "COALESCE(SUM(voice_seconds), 0), "
                    "COUNT(DISTINCT CASE WHEN voice_seconds > 0 THEN user_id END) "
                    "FROM metrics_user_hourly "
                    f"WHERE guild_id = ? AND hour_bucket >= ?{uid_filter}",
                    [guild_id, cutoff_hour, *uid_params],
                )
            else:
                # Unfiltered path: use aggregate rollup table
                cursor = await db.execute(
                    "SELECT "
                    "COALESCE(SUM(total_messages), 0), "
                    "COALESCE(SUM(unique_messagers), 0), "
                    "COALESCE(SUM(total_voice_seconds), 0), "
                    "COALESCE(SUM(unique_voice_users), 0) "
                    "FROM metrics_hourly "
                    "WHERE guild_id = ? AND hour_bucket >= ?",
                    (guild_id, cutoff_hour),
                )
            row = await cursor.fetchone()
            total_messages = row[0] if row else 0
            unique_messagers = row[1] if row else 0
            total_voice_seconds = row[2] if row else 0
            unique_voice_users = row[3] if row else 0

            # Unique users across all tracked activity sources
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT user_id) "
                "FROM metrics_user_hourly "
                f"WHERE guild_id = ? AND hour_bucket >= ?{uid_filter} "
                "AND (messages_sent > 0 OR voice_seconds > 0 OR (games_json IS NOT NULL AND games_json != '{}' AND games_json != 'null'))",
                [guild_id, cutoff_hour, *uid_params],
            )
            row = await cursor.fetchone()
            unique_users = row[0] if row else 0

            # Top games from per-user rollup JSON payloads
            cursor = await db.execute(
                "SELECT games_json "
                "FROM metrics_user_hourly "
                f"WHERE guild_id = ? AND hour_bucket >= ?{uid_filter} "
                "AND games_json IS NOT NULL AND games_json != '{}' AND games_json != 'null'",
                [guild_id, cutoff_hour, *uid_params],
            )
            game_totals: defaultdict[str, int] = defaultdict(int)
            game_samples: defaultdict[str, int] = defaultdict(int)
            for (games_json,) in await cursor.fetchall():
                try:
                    payload = json.loads(games_json) if games_json else {}
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                for game_name, seconds in payload.items():
                    if not isinstance(game_name, str):
                        continue
                    try:
                        duration = int(seconds)
                    except (TypeError, ValueError):
                        continue
                    if duration <= 0:
                        continue
                    game_totals[game_name] += duration
                    game_samples[game_name] += 1

            top_games = [
                {
                    "game_name": game_name,
                    "total_seconds": total,
                    "session_count": game_samples[game_name],
                    "avg_seconds": round(total / max(game_samples[game_name], 1)),
                }
                for game_name, total in sorted(
                    game_totals.items(), key=lambda item: item[1], reverse=True
                )[:10]
            ]

        avg_messages = round(total_messages / unique_users, 1) if unique_users else 0.0
        avg_voice = round(total_voice_seconds / unique_users) if unique_users else 0

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
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get top users by voice time."""
        self._ensure_initialized()
        cutoff_hour = _hour_bucket(int(time.time()) - (days * 86400))

        uid_filter = ""
        uid_params: list[Any] = []
        if user_ids is not None:
            if not user_ids:
                return []
            placeholders = ",".join("?" for _ in user_ids)
            uid_filter = f" AND user_id IN ({placeholders})"
            uid_params = list(user_ids)

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT user_id, SUM(voice_seconds) as total "
                "FROM metrics_user_hourly "
                f"WHERE guild_id = ? AND hour_bucket >= ? AND voice_seconds > 0{uid_filter} "
                "GROUP BY user_id ORDER BY total DESC LIMIT ?",
                [guild_id, cutoff_hour, *uid_params, limit],
            )
            return [
                {"user_id": r[0], "total_seconds": r[1]}
                for r in await cursor.fetchall()
            ]

    async def get_message_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get top users by message count."""
        self._ensure_initialized()
        cutoff_hour = _hour_bucket(int(time.time()) - (days * 86400))

        uid_filter = ""
        uid_params: list[Any] = []
        if user_ids is not None:
            if not user_ids:
                return []
            placeholders = ",".join("?" for _ in user_ids)
            uid_filter = f" AND user_id IN ({placeholders})"
            uid_params = list(user_ids)

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT user_id, SUM(messages_sent) as total "
                "FROM metrics_user_hourly "
                f"WHERE guild_id = ? AND hour_bucket >= ? AND messages_sent > 0{uid_filter} "
                "GROUP BY user_id ORDER BY total DESC LIMIT ?",
                [guild_id, cutoff_hour, *uid_params, limit],
            )
            return [
                {"user_id": r[0], "total_messages": r[1]}
                for r in await cursor.fetchall()
            ]

    async def get_timeseries(
        self,
        guild_id: int,
        metric: str = "messages",
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get hourly time-series data for a guild.

        Args:
            metric: One of "messages", "voice", "games"
            user_ids: Optional filter to specific users
        """
        self._ensure_initialized()
        cutoff_hour = _hour_bucket(int(time.time()) - (days * 86400))

        uid_filter = ""
        uid_params: list[Any] = []
        if user_ids is not None:
            if not user_ids:
                return []
            placeholders = ",".join("?" for _ in user_ids)
            uid_filter = f" AND user_id IN ({placeholders})"
            uid_params = list(user_ids)

        async with MetricsDatabase.get_connection() as db:
            if metric == "messages":
                if user_ids is not None:
                    cursor = await db.execute(
                        "SELECT hour_bucket, SUM(messages_sent), COUNT(DISTINCT user_id) "
                        "FROM metrics_user_hourly "
                        f"WHERE guild_id = ? AND hour_bucket >= ?{uid_filter} "
                        "AND messages_sent > 0 "
                        "GROUP BY hour_bucket ORDER BY hour_bucket",
                        [guild_id, cutoff_hour, *uid_params],
                    )
                else:
                    cursor = await db.execute(
                        "SELECT hour_bucket, total_messages, unique_messagers "
                        "FROM metrics_hourly "
                        "WHERE guild_id = ? AND hour_bucket >= ? "
                        "ORDER BY hour_bucket",
                        (guild_id, cutoff_hour),
                    )
                return [
                    {"timestamp": r[0], "value": r[1], "unique_users": r[2]}
                    for r in await cursor.fetchall()
                ]
            elif metric == "voice":
                if user_ids is not None:
                    cursor = await db.execute(
                        "SELECT hour_bucket, SUM(voice_seconds), COUNT(DISTINCT user_id) "
                        "FROM metrics_user_hourly "
                        f"WHERE guild_id = ? AND hour_bucket >= ?{uid_filter} "
                        "AND voice_seconds > 0 "
                        "GROUP BY hour_bucket ORDER BY hour_bucket",
                        [guild_id, cutoff_hour, *uid_params],
                    )
                else:
                    cursor = await db.execute(
                        "SELECT hour_bucket, total_voice_seconds, unique_voice_users "
                        "FROM metrics_hourly "
                        "WHERE guild_id = ? AND hour_bucket >= ? "
                        "ORDER BY hour_bucket",
                        (guild_id, cutoff_hour),
                    )
                return [
                    {"timestamp": r[0], "value": r[1], "unique_users": r[2]}
                    for r in await cursor.fetchall()
                ]
            elif metric == "games":
                cursor = await db.execute(
                    "SELECT hour_bucket, user_id, games_json "
                    "FROM metrics_user_hourly "
                    f"WHERE guild_id = ? AND hour_bucket >= ?{uid_filter} "
                    "AND games_json IS NOT NULL AND games_json != '{}' AND games_json != 'null' "
                    "ORDER BY hour_bucket",
                    [guild_id, cutoff_hour, *uid_params],
                )
                rows = await cursor.fetchall()

                by_hour_seconds: defaultdict[int, int] = defaultdict(int)
                by_hour_users: defaultdict[int, set[int]] = defaultdict(set)
                by_hour_games: defaultdict[int, defaultdict[str, int]] = defaultdict(
                    lambda: defaultdict(int)
                )

                for hour_bucket, user_id, games_json in rows:
                    try:
                        payload = json.loads(games_json) if games_json else {}
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue

                    row_total = 0
                    for game_name, seconds in payload.items():
                        if not isinstance(game_name, str):
                            continue
                        try:
                            duration = int(seconds)
                        except (TypeError, ValueError):
                            continue
                        if duration <= 0:
                            continue
                        row_total += duration
                        by_hour_games[hour_bucket][game_name] += duration

                    if row_total <= 0:
                        continue
                    by_hour_seconds[hour_bucket] += row_total
                    by_hour_users[hour_bucket].add(int(user_id))

                data: list[dict[str, Any]] = []
                for hour_bucket in sorted(by_hour_seconds):
                    game_totals = by_hour_games[hour_bucket]
                    top_game = (
                        max(game_totals.items(), key=lambda item: item[1])[0]
                        if game_totals
                        else None
                    )
                    data.append(
                        {
                            "timestamp": hour_bucket,
                            "value": by_hour_seconds[hour_bucket],
                            "unique_users": len(by_hour_users[hour_bucket]),
                            "top_game": top_game,
                        }
                    )

                return data
            else:
                return []

    async def get_top_games(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get top games by total play time."""
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)

        uid_filter = ""
        uid_params: list[Any] = []
        if user_ids is not None:
            if not user_ids:
                return []
            placeholders = ",".join("?" for _ in user_ids)
            uid_filter = f" AND user_id IN ({placeholders})"
            uid_params = list(user_ids)

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT game_name, SUM(duration_seconds) as total_time, "
                "COUNT(*) as session_count, "
                "AVG(duration_seconds) as avg_time, "
                "COUNT(DISTINCT user_id) as unique_players "
                "FROM game_sessions "
                f"WHERE guild_id = ? AND started_at >= ? AND duration_seconds IS NOT NULL{uid_filter} "
                "GROUP BY game_name ORDER BY total_time DESC LIMIT ?",
                [guild_id, cutoff, *uid_params, limit],
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

    async def get_game_metrics(
        self,
        guild_id: int,
        game_name: str,
        days: int = 7,
        limit: int = 5,
        user_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Get detailed metrics for a specific game in a guild."""
        self._ensure_initialized()
        cutoff = int(time.time()) - (days * 86400)

        uid_filter = ""
        uid_params: list[Any] = []
        if user_ids is not None:
            if not user_ids:
                return {
                    "game_name": game_name,
                    "days": days,
                    "total_seconds": 0,
                    "session_count": 0,
                    "avg_seconds": 0,
                    "unique_players": 0,
                    "top_players": [],
                    "timeseries": [],
                }
            placeholders = ",".join("?" for _ in user_ids)
            uid_filter = f" AND user_id IN ({placeholders})"
            uid_params = list(user_ids)

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0), "
                "COUNT(*), "
                "COALESCE(AVG(duration_seconds), 0), "
                "COUNT(DISTINCT user_id) "
                "FROM game_sessions "
                "WHERE guild_id = ? AND game_name = ? AND started_at >= ? "
                "AND duration_seconds IS NOT NULL"
                f"{uid_filter}",
                [guild_id, game_name, cutoff, *uid_params],
            )
            totals_row = await cursor.fetchone()

            cursor = await db.execute(
                "SELECT user_id, "
                "COALESCE(SUM(duration_seconds), 0) AS total_seconds, "
                "COUNT(*) AS session_count, "
                "COALESCE(AVG(duration_seconds), 0) AS avg_seconds "
                "FROM game_sessions "
                "WHERE guild_id = ? AND game_name = ? AND started_at >= ? "
                "AND duration_seconds IS NOT NULL"
                f"{uid_filter} "
                "GROUP BY user_id "
                "ORDER BY total_seconds DESC "
                "LIMIT ?",
                [guild_id, game_name, cutoff, *uid_params, limit],
            )
            top_players = [
                {
                    "user_id": r[0],
                    "total_seconds": r[1],
                    "session_count": r[2],
                    "avg_seconds": round(r[3]) if r[3] else 0,
                }
                for r in await cursor.fetchall()
            ]

            cursor = await db.execute(
                "SELECT (ended_at - (ended_at % 3600)) AS hour_bucket, "
                "COALESCE(SUM(duration_seconds), 0) AS total_seconds, "
                "COUNT(DISTINCT user_id) AS unique_users "
                "FROM game_sessions "
                "WHERE guild_id = ? AND game_name = ? AND ended_at IS NOT NULL "
                "AND started_at >= ? AND duration_seconds IS NOT NULL"
                f"{uid_filter} "
                "GROUP BY hour_bucket "
                "ORDER BY hour_bucket",
                [guild_id, game_name, cutoff, *uid_params],
            )
            timeseries = [
                {
                    "timestamp": r[0],
                    "value": r[1],
                    "unique_users": r[2],
                }
                for r in await cursor.fetchall()
            ]

        total_seconds = int(totals_row[0]) if totals_row else 0
        session_count = int(totals_row[1]) if totals_row else 0
        avg_seconds = round(totals_row[2]) if totals_row and totals_row[2] else 0
        unique_players = int(totals_row[3]) if totals_row else 0

        return {
            "game_name": game_name,
            "days": days,
            "total_seconds": total_seconds,
            "session_count": session_count,
            "avg_seconds": avg_seconds,
            "unique_players": unique_players,
            "top_players": top_players,
            "timeseries": timeseries,
        }

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
            voice_by_hour: dict[int, int] = {
                r[0]: r[1] for r in await cursor.fetchall()
            }

            # Game time per hour for this user
            cursor = await db.execute(
                "SELECT (ended_at - (ended_at % 3600)) as hour_bucket, SUM(duration_seconds) "
                "FROM game_sessions "
                "WHERE guild_id = ? AND user_id = ? AND ended_at IS NOT NULL AND ended_at >= ? "
                "AND duration_seconds IS NOT NULL "
                "GROUP BY hour_bucket "
                "ORDER BY hour_bucket",
                (guild_id, user_id, cutoff),
            )
            game_by_hour: dict[int, int] = {
                r[0]: r[1] for r in await cursor.fetchall()
            }

            all_hours = sorted(set(msg_by_hour) | set(voice_by_hour) | set(game_by_hour))
            timeseries = [
                {
                    "timestamp": hour_bucket,
                    "messages": msg_by_hour.get(hour_bucket, 0),
                    "voice_seconds": voice_by_hour.get(hour_bucket, 0),
                    "game_seconds": game_by_hour.get(hour_bucket, 0),
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
            self._invalidate_activity_group_counts_cache(session.guild_id)
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
            self._invalidate_activity_group_counts_cache(session.guild_id)
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
                touched_guilds: set[int] = set()
                for (guild_id, user_id, hour_bucket), count in snapshot.items():
                    touched_guilds.add(guild_id)
                    await db.execute(
                        "INSERT INTO message_counts ("
                        "guild_id, user_id, hour_bucket, bucket_seconds, message_count"
                        ") "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(guild_id, user_id, hour_bucket) "
                        "DO UPDATE SET "
                        "message_count = message_count + excluded.message_count, "
                        "bucket_seconds = excluded.bucket_seconds",
                        (guild_id, user_id, hour_bucket, 180, count),
                    )
                await db.commit()
            for guild_id in touched_guilds:
                self._invalidate_activity_group_counts_cache(guild_id)
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
                        (
                            gid,
                            hour_start,
                            total_msgs,
                            unique_msgs,
                            v_secs,
                            v_users,
                            top_game,
                        ),
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
                    msgs = next(
                        (r[2] for r in user_msg_rows if r[0] == gid and r[1] == uid), 0
                    )
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
                            deleted,
                            table,
                            self._retention_days,
                        )
                await db.commit()
        except Exception:
            self.logger.exception("Failed to purge old metrics data")

    # ------------------------------------------------------------------
    # Per-user data erasure (GDPR / Discord data deletion)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hour_bucket(epoch: int) -> int:
    """Truncate a Unix timestamp to the start of its hour."""
    return epoch - (epoch % 3600)


def _message_window_bucket(epoch: int) -> int:
    """Truncate a Unix timestamp to the start of its 3-minute message window."""
    return epoch - (epoch % 180)
