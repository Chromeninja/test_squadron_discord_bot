"""
MetricsFlushMixin — background flush/rollup/purge methods for MetricsService.

Extracted from services/metrics_service.py to keep file sizes manageable.
Do not import directly; import MetricsService from services.metrics_service.

AI Notes:
    All methods in this mixin access `self` attributes populated by
    MetricsService.__init__. Python's MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from services.db.metrics_db import MetricsDatabase
from services.metrics_buckets import hour_bucket as _hour_bucket

if TYPE_CHECKING:
    from services.metrics_models import GameSessionInfo, VoiceSessionInfo


class MetricsFlushMixin:
    """Mixin providing background task and flush/rollup/purge methods."""

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Periodically flush the message buffer to the database."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)  # type: ignore[attr-defined]
                await self._flush_message_buffer()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Error in metrics flush loop")  # type: ignore[attr-defined]
                await asyncio.sleep(5)

    async def _rollup_loop(self) -> None:
        """Periodically aggregate raw data into hourly rollups."""
        while True:
            try:
                await asyncio.sleep(self._rollup_interval)  # type: ignore[attr-defined]
                await self._perform_rollup()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Error in metrics rollup loop")  # type: ignore[attr-defined]
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
                self.logger.exception("Error in metrics purge loop")  # type: ignore[attr-defined]
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
            self._invalidate_activity_group_counts_cache(session.guild_id)  # type: ignore[attr-defined]
        except Exception:
            self.logger.exception(  # type: ignore[attr-defined]
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
            self._invalidate_activity_group_counts_cache(session.guild_id)  # type: ignore[attr-defined]
        except Exception:
            self.logger.exception(  # type: ignore[attr-defined]
                "Failed to write game session for user %d in guild %d",
                session.user_id,
                session.guild_id,
            )

    async def _flush_message_buffer(self) -> None:
        """Write buffered message counts to the database via upsert."""
        async with self._message_buffer_lock:  # type: ignore[attr-defined]
            if not self._message_buffer:  # type: ignore[attr-defined]
                return
            # Snapshot and clear
            snapshot = dict(self._message_buffer)  # type: ignore[attr-defined]
            self._message_buffer.clear()  # type: ignore[attr-defined]

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
                self._invalidate_activity_group_counts_cache(guild_id)  # type: ignore[attr-defined]
            self._last_flush_at = time.time()  # type: ignore[attr-defined]
        except Exception:
            self.logger.exception("Failed to flush message buffer")  # type: ignore[attr-defined]
            # Re-add unflushed data
            async with self._message_buffer_lock:  # type: ignore[attr-defined]
                for key, count in snapshot.items():
                    self._message_buffer[key] += count  # type: ignore[attr-defined]

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

            self._last_rollup_at = time.time()  # type: ignore[attr-defined]
            self.logger.debug("Hourly rollup completed for bucket %d", hour_start)  # type: ignore[attr-defined]

        except Exception:
            self.logger.exception("Failed to perform hourly rollup")  # type: ignore[attr-defined]

    async def _purge_old_data(self) -> None:
        """Delete metrics data older than retention_days."""
        cutoff = int(time.time()) - (self._retention_days * 86400)  # type: ignore[attr-defined]

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
                        self.logger.info(  # type: ignore[attr-defined]
                            "Purged %d rows from %s (older than %d days)",
                            deleted,
                            table,
                            self._retention_days,  # type: ignore[attr-defined]
                        )
                await db.commit()
        except Exception:
            self.logger.exception("Failed to purge old metrics data")  # type: ignore[attr-defined]
