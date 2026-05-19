from __future__ import annotations

"""Read-only DB query helpers extracted from MetricsService."""

import json
import logging
import time
from collections import defaultdict
from typing import Any

from services.db.metrics_db import MetricsDatabase
from services.metrics_buckets import hour_bucket as _hour_bucket

logger = logging.getLogger(__name__)


async def get_guild_metrics(
    guild_id: int, days: int = 7, user_ids: list[int] | None = None
) -> dict[str, Any]:
    """
    Get aggregated metrics for a guild over the given period.

    When user_ids is provided, only those users' data is included.
    """
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
    guild_id: int,
    days: int = 7,
    limit: int = 10,
    user_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Get top users by voice time."""
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
    guild_id: int,
    days: int = 7,
    limit: int = 10,
    user_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Get top users by message count."""
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
    guild_id: int,
    days: int = 7,
    limit: int = 10,
    user_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Get top games by total play time."""
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
    guild_id: int,
    game_name: str,
    days: int = 7,
    limit: int = 5,
    user_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Get detailed metrics for a specific game in a guild."""
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
    guild_id: int, user_id: int, days: int = 7
) -> dict[str, Any]:
    """Get detailed metrics for a specific user."""
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
