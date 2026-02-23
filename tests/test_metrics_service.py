"""
Tests for the MetricsService.

Tests cover:
- Message recording and buffer flush
- Voice session join/leave tracking
- Game session start/stop tracking
- Live snapshot computation
- Hourly rollup aggregation
- Data purge for retention
- Health check output
- Edge cases: duplicate joins, missing leaves, disabled service
"""

from __future__ import annotations

import asyncio
import time
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from services.db.metrics_db import MetricsDatabase
from services.metrics_service import (
    MetricsService,
    _hour_bucket,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def metrics_db(tmp_path):
    """Initialize a temporary metrics database."""
    orig_path = MetricsDatabase._db_path
    orig_init = MetricsDatabase._initialized

    MetricsDatabase._initialized = False
    MetricsDatabase._db_path = None

    db_file = tmp_path / "test_metrics.db"
    await MetricsDatabase.initialize(str(db_file))
    assert MetricsDatabase._initialized is True

    yield str(db_file)

    MetricsDatabase._db_path = orig_path
    MetricsDatabase._initialized = orig_init


@pytest_asyncio.fixture()
async def metrics_service(metrics_db):
    """Create a MetricsService in test mode (no background tasks)."""
    config_service = MagicMock()
    config_service.get.return_value = {
        "enabled": True,
        "retention_days": 90,
        "rollup_interval_minutes": 60,
        "buffer_flush_seconds": 30,
        "database_path": metrics_db,
    }
    config_service.get_guild_setting = AsyncMock(return_value=[])

    service = MetricsService(config_service, bot=None, test_mode=True)
    # Manual init since test_mode skips background tasks
    service._enabled = True
    service._initialized = True
    service._retention_days = 90
    service._db_path = metrics_db

    yield service

    await service.shutdown()


# ---------------------------------------------------------------------------
# Helper: _hour_bucket
# ---------------------------------------------------------------------------


class TestHourBucket:
    def test_truncates_to_hour(self) -> None:
        # 2026-01-01 12:34:56 UTC -> 2026-01-01 12:00:00 UTC
        ts = 1767267296  # some timestamp
        bucketed = _hour_bucket(ts)
        assert bucketed % 3600 == 0
        assert bucketed <= ts
        assert ts - bucketed < 3600

    def test_exact_hour_unchanged(self) -> None:
        ts = 3600 * 1000  # exactly on the hour
        assert _hour_bucket(ts) == ts


# ---------------------------------------------------------------------------
# Message recording
# ---------------------------------------------------------------------------


class TestRecordMessage:
    def test_increments_buffer(self, metrics_service: MetricsService) -> None:
        metrics_service.record_message(guild_id=100, user_id=1)
        metrics_service.record_message(guild_id=100, user_id=1)
        metrics_service.record_message(guild_id=100, user_id=2)

        total = sum(metrics_service._message_buffer.values())
        assert total == 3
        assert metrics_service._total_messages_buffered == 3

    def test_disabled_service_ignores(self, metrics_service: MetricsService) -> None:
        metrics_service._enabled = False
        metrics_service.record_message(guild_id=100, user_id=1)
        assert sum(metrics_service._message_buffer.values()) == 0

    def test_separate_guilds(self, metrics_service: MetricsService) -> None:
        metrics_service.record_message(guild_id=100, user_id=1)
        metrics_service.record_message(guild_id=200, user_id=1)

        # Each (guild, user, hour) key should be separate
        assert len(metrics_service._message_buffer) == 2

    def test_accepts_channel_id_parameter(self, metrics_service: MetricsService) -> None:
        metrics_service.record_message(guild_id=100, user_id=1, channel_id=123)

        total = sum(metrics_service._message_buffer.values())
        assert total == 1


class TestExcludedChannelSettings:
    @pytest.mark.asyncio
    async def test_get_excluded_channel_ids_normalizes_values(
        self, metrics_service: MetricsService
    ) -> None:
        get_setting_mock = cast(
            AsyncMock,
            metrics_service._config_service.get_guild_setting,
        )
        get_setting_mock.return_value = [
            "200",
            100,
            "invalid",
            "200",
        ]

        result = await metrics_service.get_excluded_channel_ids(123)

        assert result == {100, 200}

    @pytest.mark.asyncio
    async def test_get_excluded_channel_ids_uses_cache(
        self, metrics_service: MetricsService
    ) -> None:
        get_setting_mock = cast(
            AsyncMock,
            metrics_service._config_service.get_guild_setting,
        )
        get_setting_mock.return_value = ["100"]

        first = await metrics_service.get_excluded_channel_ids(123)
        second = await metrics_service.get_excluded_channel_ids(123)

        assert first == {100}
        assert second == {100}
        get_setting_mock.assert_awaited_once_with(
            123,
            "metrics.excluded_channel_ids",
            [],
        )

    @pytest.mark.asyncio
    async def test_get_excluded_channel_ids_dedupes_concurrent_fetches(
        self, metrics_service: MetricsService
    ) -> None:
        get_setting_mock = cast(
            AsyncMock,
            metrics_service._config_service.get_guild_setting,
        )

        async def delayed_fetch(*_args, **_kwargs):
            await asyncio.sleep(0.01)
            return ["100"]

        get_setting_mock.side_effect = delayed_fetch

        first, second = await asyncio.gather(
            metrics_service.get_excluded_channel_ids(123),
            metrics_service.get_excluded_channel_ids(123),
        )

        assert first == {100}
        assert second == {100}
        get_setting_mock.assert_awaited_once_with(
            123,
            "metrics.excluded_channel_ids",
            [],
        )


# ---------------------------------------------------------------------------
# Flush message buffer
# ---------------------------------------------------------------------------


class TestFlushMessageBuffer:
    @pytest.mark.asyncio
    async def test_flush_writes_to_db(self, metrics_service: MetricsService) -> None:
        metrics_service.record_message(guild_id=100, user_id=1)
        metrics_service.record_message(guild_id=100, user_id=1)
        metrics_service.record_message(guild_id=100, user_id=2)

        await metrics_service._flush_message_buffer()

        # Buffer should be empty after flush
        assert sum(metrics_service._message_buffer.values()) == 0

        # Verify data in DB
        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT guild_id, user_id, message_count FROM message_counts"
            )
            rows = list(await cursor.fetchall())

        assert len(rows) == 2
        totals = {r[1]: r[2] for r in rows}
        assert totals[1] == 2
        assert totals[2] == 1

    @pytest.mark.asyncio
    async def test_flush_upserts(self, metrics_service: MetricsService) -> None:
        """Flushing twice for the same hour bucket should accumulate."""
        metrics_service.record_message(guild_id=100, user_id=1)
        await metrics_service._flush_message_buffer()

        metrics_service.record_message(guild_id=100, user_id=1)
        await metrics_service._flush_message_buffer()

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT message_count FROM message_counts WHERE user_id = 1"
            )
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == 2

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_is_noop(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service._flush_message_buffer()
        # Should not raise


# ---------------------------------------------------------------------------
# Voice sessions
# ---------------------------------------------------------------------------


class TestVoiceSessions:
    @pytest.mark.asyncio
    async def test_join_creates_session(self, metrics_service: MetricsService) -> None:
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)

        key = (100, 1)
        assert key in metrics_service._voice_sessions
        session = metrics_service._voice_sessions[key]
        assert session.channel_id == 10
        assert session.joined_at > 0

    @pytest.mark.asyncio
    async def test_leave_removes_session_and_writes_db(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)
        await metrics_service.record_voice_leave(guild_id=100, user_id=1)

        assert (100, 1) not in metrics_service._voice_sessions

        # Verify session was written to DB
        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT guild_id, user_id, channel_id, duration_seconds FROM voice_sessions"
            )
            rows = list(await cursor.fetchall())

        assert len(rows) == 1
        assert rows[0][0] == 100
        assert rows[0][1] == 1
        assert rows[0][2] == 10
        assert rows[0][3] >= 0  # duration

    @pytest.mark.asyncio
    async def test_leave_without_join_is_noop(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_voice_leave(guild_id=100, user_id=99)
        # Should not raise

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM voice_sessions")
            row = await cursor.fetchone()
            assert row is not None
            count = row[0]
        assert count == 0

    @pytest.mark.asyncio
    async def test_duplicate_join_overwrites(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)

        # Second join (e.g., channel switch handled as leave+join)
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=20)
        # Old session should have been written to DB
        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM voice_sessions")
            row = await cursor.fetchone()
            assert row is not None
            count = row[0]
        assert count == 1  # old session closed

        assert metrics_service._voice_sessions[(100, 1)].channel_id == 20

    @pytest.mark.asyncio
    async def test_disabled_ignores_join(
        self, metrics_service: MetricsService
    ) -> None:
        metrics_service._enabled = False
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)
        assert len(metrics_service._voice_sessions) == 0


# ---------------------------------------------------------------------------
# Game sessions
# ---------------------------------------------------------------------------


class TestGameSessions:
    @pytest.mark.asyncio
    async def test_start_creates_session(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_game_start(
            guild_id=100, user_id=1, game_name="Star Citizen"
        )

        key = (100, 1)
        assert key in metrics_service._game_sessions
        assert metrics_service._game_sessions[key].game_name == "Star Citizen"

    @pytest.mark.asyncio
    async def test_stop_removes_and_writes_db(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_game_start(
            guild_id=100, user_id=1, game_name="Star Citizen"
        )
        await metrics_service.record_game_stop(guild_id=100, user_id=1)

        assert (100, 1) not in metrics_service._game_sessions

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute(
                "SELECT game_name, duration_seconds FROM game_sessions"
            )
            rows = list(await cursor.fetchall())

        assert len(rows) == 1
        assert rows[0][0] == "Star Citizen"
        assert rows[0][1] >= 0

    @pytest.mark.asyncio
    async def test_stop_without_start_is_noop(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_game_stop(guild_id=100, user_id=99)
        # Should not raise


# ---------------------------------------------------------------------------
# Live snapshot
# ---------------------------------------------------------------------------


class TestLiveSnapshot:
    def test_empty_snapshot(self, metrics_service: MetricsService) -> None:
        snap = metrics_service.get_live_snapshot(guild_id=100)
        assert snap.messages_today == 0
        assert snap.active_voice_users == 0
        assert snap.active_game_sessions == 0
        assert snap.top_game is None

    def test_counts_messages_today(self, metrics_service: MetricsService) -> None:
        metrics_service.record_message(guild_id=100, user_id=1)
        metrics_service.record_message(guild_id=100, user_id=2)
        metrics_service.record_message(guild_id=200, user_id=1)  # different guild

        snap = metrics_service.get_live_snapshot(guild_id=100)
        assert snap.messages_today == 2

    @pytest.mark.asyncio
    async def test_counts_voice_users(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)
        await metrics_service.record_voice_join(guild_id=100, user_id=2, channel_id=10)
        await metrics_service.record_voice_join(guild_id=200, user_id=3, channel_id=20)

        snap = metrics_service.get_live_snapshot(guild_id=100)
        assert snap.active_voice_users == 2

    @pytest.mark.asyncio
    async def test_counts_game_sessions(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_game_start(
            guild_id=100, user_id=1, game_name="Star Citizen"
        )
        await metrics_service.record_game_start(
            guild_id=100, user_id=2, game_name="Star Citizen"
        )
        await metrics_service.record_game_start(
            guild_id=100, user_id=3, game_name="EVE Online"
        )

        snap = metrics_service.get_live_snapshot(guild_id=100)
        assert snap.active_game_sessions == 3  # 3 active sessions
        assert snap.top_game == "Star Citizen"  # 2 players vs 1


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------


class TestQueryMethods:
    @pytest.mark.asyncio
    async def test_get_guild_metrics_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_guild_metrics(guild_id=100, days=7)
        assert result["total_messages"] == 0
        assert result["total_voice_seconds"] == 0
        assert result["top_games"] == []

    @pytest.mark.asyncio
    async def test_get_voice_leaderboard_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_voice_leaderboard(guild_id=100, days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_message_leaderboard_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_message_leaderboard(guild_id=100, days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_timeseries_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_timeseries(guild_id=100, metric="messages", days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_timeseries_invalid_metric(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_timeseries(guild_id=100, metric="invalid", days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_user_metrics_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_user_metrics(guild_id=100, user_id=1, days=7)
        assert result["total_messages"] == 0
        assert result["total_voice_seconds"] == 0
        assert result["top_games"] == []

    @pytest.mark.asyncio
    async def test_query_methods_use_hourly_rollups(
        self, metrics_service: MetricsService
    ) -> None:
        now_bucket = _hour_bucket(int(time.time()))
        hour_1 = now_bucket - 7200
        hour_2 = now_bucket - 3600

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO metrics_hourly "
                "(guild_id, hour_bucket, total_messages, unique_messagers, total_voice_seconds, unique_voice_users, top_game) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (100, hour_1, 15, 5, 300, 3, "Star Citizen"),
            )
            await db.execute(
                "INSERT INTO metrics_hourly "
                "(guild_id, hour_bucket, total_messages, unique_messagers, total_voice_seconds, unique_voice_users, top_game) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (100, hour_2, 5, 2, 120, 2, "EVE Online"),
            )

            await db.execute(
                "INSERT INTO metrics_user_hourly "
                "(guild_id, user_id, hour_bucket, messages_sent, voice_seconds, games_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 1, hour_1, 10, 200, '{"Star Citizen": 200}'),
            )
            await db.execute(
                "INSERT INTO metrics_user_hourly "
                "(guild_id, user_id, hour_bucket, messages_sent, voice_seconds, games_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 2, hour_1, 5, 100, '{"Star Citizen": 100}'),
            )
            await db.execute(
                "INSERT INTO metrics_user_hourly "
                "(guild_id, user_id, hour_bucket, messages_sent, voice_seconds, games_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 1, hour_2, 3, 60, '{"EVE Online": 60}'),
            )
            await db.execute(
                "INSERT INTO metrics_user_hourly "
                "(guild_id, user_id, hour_bucket, messages_sent, voice_seconds, games_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 3, hour_2, 2, 60, None),
            )
            await db.commit()

        guild_metrics = await metrics_service.get_guild_metrics(guild_id=100, days=7)
        assert guild_metrics["total_messages"] == 20
        assert guild_metrics["unique_messagers"] == 7
        assert guild_metrics["total_voice_seconds"] == 420
        assert guild_metrics["unique_voice_users"] == 5
        assert guild_metrics["unique_users"] == 3
        assert guild_metrics["top_games"][0]["game_name"] == "Star Citizen"
        assert guild_metrics["top_games"][0]["total_seconds"] == 300

        voice_lb = await metrics_service.get_voice_leaderboard(guild_id=100, days=7)
        assert voice_lb[0]["user_id"] == 1
        assert voice_lb[0]["total_seconds"] == 260

        msg_lb = await metrics_service.get_message_leaderboard(guild_id=100, days=7)
        assert msg_lb[0]["user_id"] == 1
        assert msg_lb[0]["total_messages"] == 13

        msg_series = await metrics_service.get_timeseries(guild_id=100, metric="messages", days=7)
        assert [point["value"] for point in msg_series] == [15, 5]

        voice_series = await metrics_service.get_timeseries(guild_id=100, metric="voice", days=7)
        assert [point["value"] for point in voice_series] == [300, 120]

        games_series = await metrics_service.get_timeseries(guild_id=100, metric="games", days=7)
        assert [point["top_game"] for point in games_series] == ["Star Citizen", "EVE Online"]

    @pytest.mark.asyncio
    async def test_get_top_games_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_top_games(guild_id=100, days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_top_games_with_data(
        self, metrics_service: MetricsService
    ) -> None:
        """Insert game sessions directly and query top games."""
        now = int(time.time())
        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 1, "Star Citizen", now - 7200, now - 3600, 3600),
            )
            await db.execute(
                "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 2, "Star Citizen", now - 7200, now - 5400, 1800),
            )
            await db.execute(
                "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 1, "EVE Online", now - 3600, now, 3600),
            )
            await db.commit()

        result = await metrics_service.get_top_games(guild_id=100, days=7)
        assert len(result) == 2
        # Star Citizen: 5400s total, EVE Online: 3600s
        assert result[0]["game_name"] == "Star Citizen"
        assert result[0]["total_seconds"] == 5400
        assert result[0]["unique_players"] == 2
        assert result[1]["game_name"] == "EVE Online"


# ---------------------------------------------------------------------------
# Purge old data
# ---------------------------------------------------------------------------


class TestPurgeOldData:
    @pytest.mark.asyncio
    async def test_purge_deletes_old_rows(
        self, metrics_service: MetricsService
    ) -> None:
        metrics_service._retention_days = 1
        old_ts = int(time.time()) - 200_000  # > 2 days ago

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO voice_sessions (guild_id, user_id, channel_id, joined_at, left_at, duration_seconds) "
                "VALUES (100, 1, 10, ?, ?, 3600)",
                (old_ts, old_ts + 3600),
            )
            await db.execute(
                "INSERT INTO message_counts (guild_id, user_id, hour_bucket, message_count) "
                "VALUES (100, 1, ?, 5)",
                (old_ts,),
            )
            await db.commit()

        await metrics_service._purge_old_data()

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM voice_sessions")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 0

            cursor = await db.execute("SELECT COUNT(*) FROM message_counts")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 0

    @pytest.mark.asyncio
    async def test_purge_keeps_recent_rows(
        self, metrics_service: MetricsService
    ) -> None:
        metrics_service._retention_days = 90
        recent_ts = int(time.time()) - 3600  # 1 hour ago

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO voice_sessions (guild_id, user_id, channel_id, joined_at, left_at, duration_seconds) "
                "VALUES (100, 1, 10, ?, ?, 3600)",
                (recent_ts, recent_ts + 3600),
            )
            await db.commit()

        await metrics_service._purge_old_data()

        async with MetricsDatabase.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM voice_sessions")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 1


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_returns_status(
        self, metrics_service: MetricsService
    ) -> None:
        health = await metrics_service.health_check()
        assert health["service"] == "metrics"
        assert health["initialized"] is True
        assert health["enabled"] is True
        assert "active_voice_sessions" in health
        assert "message_buffer_size" in health

    @pytest.mark.asyncio
    async def test_health_check_counts_sessions(
        self, metrics_service: MetricsService
    ) -> None:
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)
        metrics_service.record_message(guild_id=100, user_id=1)

        health = await metrics_service.health_check()
        assert health["active_voice_sessions"] == 1
        assert health["message_buffer_size"] == 1
        assert health["total_messages_buffered"] == 1
