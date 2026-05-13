"""
MetricsReadMixin — read/query methods for MetricsService.

Extracted from services/metrics_service.py to keep file sizes manageable.
Do not import directly; import MetricsService from services.metrics_service.

AI Notes:
    All methods in this mixin access `self` attributes populated by
    MetricsService.__init__. Python's MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import services.metrics_queries as _queries
from services.db.metrics_db import MetricsDatabase
from services.metrics_activity import classify_member_activity_tiers


class MetricsReadMixin:
    """Mixin providing read/query methods for MetricsService."""

    # ------------------------------------------------------------------
    # Config-backed cache helpers
    # ------------------------------------------------------------------

    async def get_excluded_channel_ids(
        self, guild_id: int, *, force_refresh: bool = False
    ) -> set[int]:
        """Return excluded channel IDs for metrics collection in this guild."""
        async with self._excluded_channels_lock:  # type: ignore[attr-defined]
            now = time.monotonic()
            cached = self._excluded_channels_cache.get(guild_id)  # type: ignore[attr-defined]
            if (
                not force_refresh
                and cached is not None
                and (now - cached[0]) < self._excluded_channels_ttl_seconds  # type: ignore[attr-defined]
            ):
                return set(cached[1])

            raw_value = await self._config_service.get_guild_setting(  # type: ignore[attr-defined]
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

            self._excluded_channels_cache[guild_id] = (time.monotonic(), parsed)  # type: ignore[attr-defined]
            return set(parsed)

    async def get_tracked_game_config(
        self, guild_id: int, *, force_refresh: bool = False
    ) -> tuple[str, set[str]]:
        """Return (mode, game_names) for activity-group game tracking.

        mode is 'all' or 'specific'. When 'all', game_names is empty and
        every game counts. When 'specific', only games in game_names count.
        """
        async with self._tracked_games_lock:  # type: ignore[attr-defined]
            now = time.monotonic()
            cached = self._tracked_games_cache.get(guild_id)  # type: ignore[attr-defined]
            if (
                not force_refresh
                and cached is not None
                and (now - cached[0]) < self._tracked_games_ttl_seconds  # type: ignore[attr-defined]
            ):
                return cached[1], set(cached[2])

            mode_raw = await self._config_service.get_guild_setting(  # type: ignore[attr-defined]
                guild_id, "metrics.tracked_games_mode", "all"
            )
            mode = mode_raw if mode_raw in ("all", "specific") else "all"

            games_raw = await self._config_service.get_guild_setting(  # type: ignore[attr-defined]
                guild_id, "metrics.tracked_games", []
            )
            games: set[str] = set()
            if isinstance(games_raw, list):
                for item in games_raw:
                    name = str(item).strip()
                    if name:
                        games.add(name)

            self._tracked_games_cache[guild_id] = (time.monotonic(), mode, games)  # type: ignore[attr-defined]
            return mode, set(games)

    async def get_activity_thresholds(
        self, guild_id: int, *, force_refresh: bool = False
    ) -> tuple[int, int, int]:
        """Return (min_voice_seconds, min_game_seconds, min_messages) for a guild.

        Defaults: 15 min voice, 15 min game, 5 messages.
        Values are cached with 30s TTL.
        """
        # Fast-path: read cache under lock, return if valid.
        async with self._activity_thresholds_lock:  # type: ignore[attr-defined]
            now = time.monotonic()
            cached = self._activity_thresholds_cache.get(guild_id)  # type: ignore[attr-defined]
            if (
                not force_refresh
                and cached is not None
                and (now - cached[0]) < self._activity_thresholds_ttl_seconds  # type: ignore[attr-defined]
            ):
                return cached[1], cached[2], cached[3]

        # Fetch and parse outside the lock to reduce contention.
        raw_voice = await self._config_service.get_guild_setting(  # type: ignore[attr-defined]
            guild_id,
            "metrics.min_voice_minutes",
            15,
        )
        raw_game = await self._config_service.get_guild_setting(  # type: ignore[attr-defined]
            guild_id,
            "metrics.min_game_minutes",
            15,
        )
        raw_msgs = await self._config_service.get_guild_setting(  # type: ignore[attr-defined]
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
        async with self._activity_thresholds_lock:  # type: ignore[attr-defined]
            self._activity_thresholds_cache[guild_id] = (  # type: ignore[attr-defined]
                time.monotonic(),
                min_voice_secs,
                min_game_secs,
                min_msgs,
            )
        return min_voice_secs, min_game_secs, min_msgs

    # ------------------------------------------------------------------
    # Activity-group bucket computation
    # ------------------------------------------------------------------

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
        self._ensure_initialized()  # type: ignore[attr-defined]
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
                "SELECT user_id, CAST(hour_bucket / 86400 AS INTEGER) AS day_bucket, "
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
            (chat_days_by_user, last_chat),
            (voice_days_by_user, last_voice),
            (game_days_by_user, last_game),
        ) = await asyncio.gather(
            _fetch_chat_activity(),
            _fetch_voice_activity(),
            _fetch_game_activity(),
        )

        for uid, days_set in chat_days_by_user.items():
            entry = user_data.setdefault(uid, {})
            entry["active_chat_days"] = days_set
            entry["last_chat_at"] = last_chat.get(uid, 0)

        for uid, days_set in voice_days_by_user.items():
            entry = user_data.setdefault(uid, {})
            entry["active_voice_days"] = days_set
            entry["last_voice_at"] = last_voice.get(uid, 0)

        for uid, days_set in game_days_by_user.items():
            entry = user_data.setdefault(uid, {})
            entry["active_game_days"] = days_set
            entry["last_game_at"] = last_game.get(uid, 0)

        return classify_member_activity_tiers(
            user_data,
            range_start_day,
            normalized_lookback,
        )

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
        async with self._activity_group_counts_lock:  # type: ignore[attr-defined]
            cached = self._activity_group_counts_cache.get(cache_key)  # type: ignore[attr-defined]
            if cached is not None:
                cached_ts, cached_counts = cached
                if (
                    time.monotonic() - cached_ts
                    < self._activity_group_counts_ttl_seconds  # type: ignore[attr-defined]
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

        async with self._activity_group_counts_lock:  # type: ignore[attr-defined]
            self._activity_group_counts_cache[cache_key] = (  # type: ignore[attr-defined]
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
            self._activity_group_counts_cache.clear()  # type: ignore[attr-defined]
            return

        keys_to_delete = [
            key for key in self._activity_group_counts_cache  # type: ignore[attr-defined]
            if key[0] == guild_id
        ]
        for key in keys_to_delete:
            self._activity_group_counts_cache.pop(key, None)  # type: ignore[attr-defined]

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

    async def get_messages_today(self, guild_id: int) -> int:
        """Return today's message total (UTC) from DB plus current in-memory buffer.

        AI Notes:
            The dashboard "Live" row should represent current day totals, not
            only unflushed in-memory increments.  We combine persisted rows from
            ``message_counts`` with the current buffer to avoid dropping to zero
            between flushes or after process restarts.
        """
        self._ensure_initialized()  # type: ignore[attr-defined]

        now = int(time.time())
        today_start = now - (now % 86400)  # midnight UTC

        # Capture current in-memory increments for today.
        async with self._message_buffer_lock:  # type: ignore[attr-defined]
            buffered_today = sum(
                count
                for (gid, _uid, bucket), count in self._message_buffer.items()  # type: ignore[attr-defined]
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
            self.logger.exception(  # type: ignore[attr-defined]
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
        """Get aggregated metrics for a guild over the given period."""
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_guild_metrics(guild_id, days, user_ids)

    async def get_voice_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get top users by voice time."""
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_voice_leaderboard(guild_id, days, limit, user_ids)

    async def get_message_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get top users by message count."""
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_message_leaderboard(guild_id, days, limit, user_ids)

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
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_timeseries(guild_id, metric, days, user_ids)

    async def get_top_games(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get top games by total play time."""
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_top_games(guild_id, days, limit, user_ids)

    async def get_game_metrics(
        self,
        guild_id: int,
        game_name: str,
        days: int = 7,
        limit: int = 5,
        user_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Get detailed metrics for a specific game in a guild."""
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_game_metrics(guild_id, game_name, days, limit, user_ids)

    async def get_user_metrics(
        self, guild_id: int, user_id: int, days: int = 7
    ) -> dict[str, Any]:
        """Get detailed metrics for a specific user."""
        self._ensure_initialized()  # type: ignore[attr-defined]
        return await _queries.get_user_metrics(guild_id, user_id, days)
