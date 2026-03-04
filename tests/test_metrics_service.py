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

    async def _mock_guild_setting(
        guild_id: int,
        key: str,
        default: object = None,
    ) -> object:
        """Return sane test defaults for guild settings.

        Threshold keys return 0 (no minimum) so existing tests pass.
        Everything else returns [] (no excluded channels, etc.).
        """
        _zero_keys = {
            "metrics.min_voice_minutes",
            "metrics.min_game_minutes",
            "metrics.min_messages",
        }
        if key in _zero_keys:
            return 0
        return default if default is not None else []

    config_service.get_guild_setting = AsyncMock(side_effect=_mock_guild_setting)

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

    def test_accepts_channel_id_parameter(
        self, metrics_service: MetricsService
    ) -> None:
        metrics_service.record_message(guild_id=100, user_id=1, channel_id=123)

        total = sum(metrics_service._message_buffer.values())
        assert total == 1


class TestExcludedChannelSettings:
    @pytest.mark.asyncio
    async def test_get_excluded_channel_ids_normalizes_values(
        self, metrics_service: MetricsService
    ) -> None:
        get_setting_mock = cast(
            "AsyncMock",
            metrics_service._config_service.get_guild_setting,
        )
        get_setting_mock.side_effect = None
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
            "AsyncMock",
            metrics_service._config_service.get_guild_setting,
        )
        get_setting_mock.side_effect = None
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
            "AsyncMock",
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
    async def test_disabled_ignores_join(self, metrics_service: MetricsService) -> None:
        metrics_service._enabled = False
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)
        assert len(metrics_service._voice_sessions) == 0


# ---------------------------------------------------------------------------
# Game sessions
# ---------------------------------------------------------------------------


class TestGameSessions:
    @pytest.mark.asyncio
    async def test_start_creates_session(self, metrics_service: MetricsService) -> None:
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
    async def test_counts_voice_users(self, metrics_service: MetricsService) -> None:
        await metrics_service.record_voice_join(guild_id=100, user_id=1, channel_id=10)
        await metrics_service.record_voice_join(guild_id=100, user_id=2, channel_id=10)
        await metrics_service.record_voice_join(guild_id=200, user_id=3, channel_id=20)

        snap = metrics_service.get_live_snapshot(guild_id=100)
        assert snap.active_voice_users == 2

    @pytest.mark.asyncio
    async def test_counts_game_sessions(self, metrics_service: MetricsService) -> None:
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


class TestMessagesToday:
    @pytest.mark.asyncio
    async def test_get_messages_today_includes_persisted_and_buffered(
        self, metrics_service: MetricsService
    ) -> None:
        now = int(time.time())
        today_start = now - (now % 86400)

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO message_counts "
                "(guild_id, user_id, hour_bucket, bucket_seconds, message_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (100, 1, today_start, 180, 4),
            )
            await db.commit()

        metrics_service.record_message(guild_id=100, user_id=2)
        metrics_service.record_message(guild_id=100, user_id=3)

        total = await metrics_service.get_messages_today(guild_id=100)

        assert total == 6

    @pytest.mark.asyncio
    async def test_get_messages_today_excludes_other_guild_and_old_rows(
        self, metrics_service: MetricsService
    ) -> None:
        now = int(time.time())
        today_start = now - (now % 86400)
        yesterday = today_start - 180

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO message_counts "
                "(guild_id, user_id, hour_bucket, bucket_seconds, message_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (100, 1, yesterday, 180, 10),
            )
            await db.execute(
                "INSERT INTO message_counts "
                "(guild_id, user_id, hour_bucket, bucket_seconds, message_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (200, 1, today_start, 180, 10),
            )
            await db.execute(
                "INSERT INTO message_counts "
                "(guild_id, user_id, hour_bucket, bucket_seconds, message_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (100, 2, today_start, 180, 3),
            )
            await db.commit()

        metrics_service.record_message(guild_id=200, user_id=9)

        total = await metrics_service.get_messages_today(guild_id=100)

        assert total == 3


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
    async def test_get_timeseries_empty(self, metrics_service: MetricsService) -> None:
        result = await metrics_service.get_timeseries(
            guild_id=100, metric="messages", days=7
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_timeseries_invalid_metric(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_timeseries(
            guild_id=100, metric="invalid", days=7
        )
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

        msg_series = await metrics_service.get_timeseries(
            guild_id=100, metric="messages", days=7
        )
        assert [point["value"] for point in msg_series] == [15, 5]

        voice_series = await metrics_service.get_timeseries(
            guild_id=100, metric="voice", days=7
        )
        assert [point["value"] for point in voice_series] == [300, 120]

        games_series = await metrics_service.get_timeseries(
            guild_id=100, metric="games", days=7
        )
        assert [point["value"] for point in games_series] == [300, 60]
        assert [point["unique_users"] for point in games_series] == [2, 1]
        assert [point["top_game"] for point in games_series] == [
            "Star Citizen",
            "EVE Online",
        ]

        filtered_games_series = await metrics_service.get_timeseries(
            guild_id=100,
            metric="games",
            days=7,
            user_ids=[2],
        )
        assert len(filtered_games_series) == 1
        assert filtered_games_series[0]["value"] == 100
        assert filtered_games_series[0]["unique_users"] == 1
        assert filtered_games_series[0]["top_game"] == "Star Citizen"

    @pytest.mark.asyncio
    async def test_get_top_games_empty(self, metrics_service: MetricsService) -> None:
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

    @pytest.mark.asyncio
    async def test_get_game_metrics_with_top_players_and_timeseries(
        self, metrics_service: MetricsService
    ) -> None:
        """Returns per-game totals, top players, and hourly trend data."""
        now = int(time.time())
        hour_1 = now - 7200
        hour_2 = now - 3600

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 1, "Star Citizen", hour_1 - 300, hour_1, 3600),
            )
            await db.execute(
                "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 2, "Star Citizen", hour_2 - 300, hour_2, 1800),
            )
            await db.execute(
                "INSERT INTO game_sessions (guild_id, user_id, game_name, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (100, 1, "Star Citizen", hour_2 - 200, hour_2, 1200),
            )
            await db.commit()

        result = await metrics_service.get_game_metrics(
            guild_id=100,
            game_name="Star Citizen",
            days=7,
            limit=5,
        )

        assert result["game_name"] == "Star Citizen"
        assert result["total_seconds"] == 6600
        assert result["session_count"] == 3
        assert result["unique_players"] == 2
        assert len(result["top_players"]) == 2
        assert result["top_players"][0]["user_id"] == 1
        assert result["top_players"][0]["total_seconds"] == 4800
        assert len(result["timeseries"]) >= 2


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


# ---------------------------------------------------------------------------
# Tier derivation (cadence-based)
# ---------------------------------------------------------------------------


class TestTierFromCadence:
    """Unit tests for the static _tier_from_cadence helper.

    Cadence tiers divide the lookback range into non-overlapping windows
    and require activity in *every* window to qualify.
    """

    # -- empty / no activity --------------------------------------------------

    def test_empty_active_days_is_inactive(self) -> None:
        assert MetricsService._tier_from_cadence(set(), 0, 7) == "inactive"

    # -- 7-day range -----------------------------------------------------------

    def test_7d_all_days_is_hardcore(self) -> None:
        """Active every day for 7 days → hardcore."""
        start = 20000
        days_set = set(range(start, start + 7))
        assert MetricsService._tier_from_cadence(days_set, start, 7) == "hardcore"

    def test_7d_miss_one_day_not_hardcore(self) -> None:
        """Missing one day out of 7 → not hardcore."""
        start = 20000
        days_set = {start, start + 1, start + 2, start + 3, start + 4, start + 6}
        assert MetricsService._tier_from_cadence(days_set, start, 7) != "hardcore"

    def test_7d_every_3day_window_is_regular(self) -> None:
        """Active once per 3-day window across 7 days → regular.

        Windows: [0-2], [3-5], [6-6].  Need activity in each."""
        start = 20000
        days_set = {start + 1, start + 4, start + 6}  # one per window
        assert MetricsService._tier_from_cadence(days_set, start, 7) == "regular"

    def test_7d_miss_one_3day_window_is_casual(self) -> None:
        """Missing activity in one 3-day window falls to casual (1 window of 7d)."""
        start = 20000
        days_set = {start + 1, start + 6}  # miss window [3-5]
        assert MetricsService._tier_from_cadence(days_set, start, 7) == "casual"

    def test_7d_any_activity_is_at_least_casual(self) -> None:
        """Any activity at all in a 7-day range is casual (1 window)."""
        start = 20000
        days_set = {start + 3}
        assert MetricsService._tier_from_cadence(days_set, start, 7) == "casual"

    def test_7d_reserve_skipped(self) -> None:
        """Reserve (30d window) is skipped for 7-day range.

        A user who only meets casual but not regular should be casual,
        not fall through to reserve."""
        start = 20000
        days_set = {start}
        result = MetricsService._tier_from_cadence(days_set, start, 7)
        assert result == "casual"

    # -- 30-day range ----------------------------------------------------------

    def test_30d_all_days_is_hardcore(self) -> None:
        start = 20000
        days_set = set(range(start, start + 30))
        assert MetricsService._tier_from_cadence(days_set, start, 30) == "hardcore"

    def test_30d_every_3_days_is_regular(self) -> None:
        """Active once per 3-day window across 30 days → regular."""
        start = 20000
        days_set = {start + i * 3 for i in range(10)}
        assert MetricsService._tier_from_cadence(days_set, start, 30) == "regular"

    def test_30d_every_7_days_is_casual(self) -> None:
        """Active once per 7-day window across 30 days → casual.

        30 / 7 = 5 windows (4 full + 1 partial of 2 days)."""
        start = 20000
        days_set = {start + i * 7 for i in range(5)}
        assert MetricsService._tier_from_cadence(days_set, start, 30) == "casual"

    def test_30d_any_activity_at_least_reserve(self) -> None:
        """Any activity in 30-day range qualifies as reserve (1 window of 30d)."""
        start = 20000
        days_set = {start + 15}
        assert MetricsService._tier_from_cadence(days_set, start, 30) == "reserve"

    def test_30d_miss_one_7d_window_is_reserve(self) -> None:
        """Hitting 4 of 5 weekly windows → falls to reserve."""
        start = 20000
        days_set = {start + 0, start + 7, start + 14, start + 28}  # miss [21-27]
        assert MetricsService._tier_from_cadence(days_set, start, 30) == "reserve"

    # -- 90-day range ----------------------------------------------------------

    def test_90d_all_days_is_hardcore(self) -> None:
        start = 20000
        days_set = set(range(start, start + 90))
        assert MetricsService._tier_from_cadence(days_set, start, 90) == "hardcore"

    def test_90d_every_3_days_is_regular(self) -> None:
        start = 20000
        days_set = {start + i * 3 for i in range(30)}
        assert MetricsService._tier_from_cadence(days_set, start, 90) == "regular"

    def test_90d_every_7_days_is_casual(self) -> None:
        start = 20000
        days_set = {start + i * 7 for i in range(13)}
        assert MetricsService._tier_from_cadence(days_set, start, 90) == "casual"

    def test_90d_every_30_days_is_reserve(self) -> None:
        """Active once per 30-day block across 90 days → reserve."""
        start = 20000
        days_set = {start + 5, start + 35, start + 65}
        assert MetricsService._tier_from_cadence(days_set, start, 90) == "reserve"

    def test_90d_miss_one_30d_block_is_inactive(self) -> None:
        """Missing activity in one 30-day block → inactive."""
        start = 20000
        days_set = {start + 5, start + 65}  # miss [30-59]
        assert MetricsService._tier_from_cadence(days_set, start, 90) == "inactive"

    # -- edge cases ------------------------------------------------------------

    def test_single_day_range_single_activity_is_hardcore(self) -> None:
        """Range of 1 day with activity ⇒ hardcore (1 window of 1 day)."""
        start = 20000
        assert MetricsService._tier_from_cadence({start}, start, 1) == "hardcore"

    def test_single_day_range_no_activity_is_inactive(self) -> None:
        assert MetricsService._tier_from_cadence(set(), 20000, 1) == "inactive"


# ---------------------------------------------------------------------------
# Activity bucket computation (integration)
# ---------------------------------------------------------------------------


class TestActivityBuckets:
    """Integration tests for get_member_activity_buckets with real DB.

    With cadence-based tiers, a single recording on one day only qualifies
    as 'hardcore' when lookback_days=1 (one window of 1 day).  For longer
    ranges the user won't meet every window.
    """

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(
        self, metrics_service: MetricsService
    ) -> None:
        result = await metrics_service.get_member_activity_buckets(guild_id=999)
        assert result == {}

    @pytest.mark.asyncio
    async def test_chat_activity_populates_chat_tier(
        self, metrics_service: MetricsService
    ) -> None:
        now = int(time.time())
        metrics_service.record_message(guild_id=100, user_id=1, channel_id=10)
        await metrics_service._flush_message_buffer()

        # lookback_days=1 → single-day window, today's activity = hardcore
        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 1 in result
        assert result[1]["chat_tier"] == "hardcore"
        # voice_tier should be inactive since there's no voice data
        assert result[1].get("voice_tier", "inactive") == "inactive"

    @pytest.mark.asyncio
    async def test_voice_activity_populates_voice_tier(
        self, metrics_service: MetricsService
    ) -> None:
        now = int(time.time())
        await metrics_service.record_voice_join(guild_id=100, user_id=2, channel_id=10)
        await metrics_service.record_voice_leave(guild_id=100, user_id=2)

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 2 in result
        assert result[2]["voice_tier"] == "hardcore"

    @pytest.mark.asyncio
    async def test_combined_tier_merges_dimensions(
        self, metrics_service: MetricsService
    ) -> None:
        now = int(time.time())
        metrics_service.record_message(guild_id=100, user_id=3, channel_id=10)
        await metrics_service._flush_message_buffer()
        await metrics_service.record_voice_join(guild_id=100, user_id=3, channel_id=10)
        await metrics_service.record_voice_leave(guild_id=100, user_id=3)

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 3 in result
        assert result[3]["combined_tier"] == "hardcore"

    @pytest.mark.asyncio
    async def test_single_day_activity_in_30d_range_is_reserve(
        self, metrics_service: MetricsService
    ) -> None:
        """One day of activity in a 30-day range → reserve (1 window of 30d)."""
        now = int(time.time())
        metrics_service.record_message(guild_id=100, user_id=4, channel_id=10)
        await metrics_service._flush_message_buffer()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=30,
            now_utc=now,
        )
        assert 4 in result
        assert result[4]["chat_tier"] == "reserve"

    @pytest.mark.asyncio
    async def test_group_counts_structure(
        self, metrics_service: MetricsService
    ) -> None:
        metrics_service.record_message(guild_id=100, user_id=1, channel_id=10)
        await metrics_service._flush_message_buffer()

        counts = await metrics_service.get_activity_group_counts(guild_id=100)
        assert "voice" in counts
        assert "chat" in counts
        assert "game" in counts
        assert "combined" in counts
        for dim_counts in counts.values():
            for tier in ("hardcore", "regular", "casual", "reserve", "inactive"):
                assert tier in dim_counts

    @pytest.mark.asyncio
    async def test_get_user_ids_for_tier(self, metrics_service: MetricsService) -> None:
        metrics_service.record_message(guild_id=100, user_id=1, channel_id=10)
        await metrics_service._flush_message_buffer()

        # lookback_days=1 → single activity today = hardcore
        ids = await metrics_service.get_activity_group_user_ids(
            guild_id=100,
            dimension="chat",
            tier="hardcore",
            lookback_days=1,
        )
        assert 1 in ids

    @pytest.mark.asyncio
    async def test_get_user_ids_bulk(self, metrics_service: MetricsService) -> None:
        """Bulk endpoint returns matching IDs for multiple dimension+tier combos."""
        metrics_service.record_message(guild_id=100, user_id=1, channel_id=10)
        await metrics_service._flush_message_buffer()
        await metrics_service.record_voice_join(guild_id=100, user_id=2, channel_id=10)
        await metrics_service.record_voice_leave(guild_id=100, user_id=2)

        result = await metrics_service.get_activity_group_user_ids_bulk(
            guild_id=100,
            dimensions=["chat", "voice"],
            tiers=["hardcore", "inactive"],
            lookback_days=1,
        )
        assert "chat" in result
        assert "voice" in result
        assert 1 in result["chat"]["hardcore"]
        assert 2 in result["voice"]["hardcore"]

    @pytest.mark.asyncio
    async def test_get_user_ids_bulk_empty(
        self, metrics_service: MetricsService
    ) -> None:
        """Bulk endpoint returns empty lists when no activity matches."""
        result = await metrics_service.get_activity_group_user_ids_bulk(
            guild_id=999,
            dimensions=["voice"],
            tiers=["hardcore"],
        )
        assert result == {"voice": {"hardcore": []}}


# ---------------------------------------------------------------------------
# Activity threshold filtering
# ---------------------------------------------------------------------------


class TestActivityThresholds:
    """Verify that per-day minimum thresholds filter activity correctly."""

    @pytest.mark.asyncio
    async def test_chat_below_threshold_excluded(
        self, metrics_service: MetricsService
    ) -> None:
        """Days with fewer messages than min_messages are not counted."""
        now = int(time.time())

        # Set threshold to 5 messages
        async def _high_chat_threshold(
            guild_id: int,
            key: str,
            default: object = None,
        ) -> object:
            if key == "metrics.min_messages":
                return 5
            if key in ("metrics.min_voice_minutes", "metrics.min_game_minutes"):
                return 0
            return default if default is not None else []

        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=_high_chat_threshold,
        )
        # Clear threshold cache
        metrics_service._activity_thresholds_cache.clear()

        # Record only 3 messages — below the 5-message threshold
        for _ in range(3):
            metrics_service.record_message(guild_id=100, user_id=1, channel_id=10)
        await metrics_service._flush_message_buffer()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        # User should be absent (no qualifying days)
        assert 1 not in result

    @pytest.mark.asyncio
    async def test_chat_at_threshold_included(
        self, metrics_service: MetricsService, monkeypatch
    ) -> None:
        """Days with min_messages distinct 3-minute windows are counted."""
        base_now = int(time.time())

        async def _threshold_5(
            guild_id: int,
            key: str,
            default: object = None,
        ) -> object:
            if key == "metrics.min_messages":
                return 5
            if key in ("metrics.min_voice_minutes", "metrics.min_game_minutes"):
                return 0
            return default if default is not None else []

        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=_threshold_5,
        )
        metrics_service._activity_thresholds_cache.clear()

        # Record 5 messages 3+ minutes apart — exactly at threshold
        for i in range(5):
            ts = base_now + (i * 181)
            monkeypatch.setattr("services.metrics_service.time.time", lambda ts=ts: ts)
            metrics_service.record_message(guild_id=100, user_id=2, channel_id=10)
        await metrics_service._flush_message_buffer()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=base_now + (4 * 181),
        )
        assert 2 in result
        assert result[2]["chat_tier"] == "hardcore"

    @pytest.mark.asyncio
    async def test_chat_burst_messages_same_window_included(
        self, metrics_service: MetricsService
    ) -> None:
        """Burst messages in one 3-minute window still satisfy min_messages."""
        now = int(time.time())

        async def _threshold_5(
            guild_id: int,
            key: str,
            default: object = None,
        ) -> object:
            if key == "metrics.min_messages":
                return 5
            if key in ("metrics.min_voice_minutes", "metrics.min_game_minutes"):
                return 0
            return default if default is not None else []

        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=_threshold_5,
        )
        metrics_service._activity_thresholds_cache.clear()

        # 5 rapid messages in the same 3-minute window => 5 total messages
        for _ in range(5):
            metrics_service.record_message(guild_id=100, user_id=6, channel_id=10)
        await metrics_service._flush_message_buffer()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 6 in result
        assert result[6]["chat_tier"] == "hardcore"

    @pytest.mark.asyncio
    async def test_voice_below_threshold_excluded(
        self, metrics_service: MetricsService
    ) -> None:
        """Voice sessions shorter than min_voice_minutes are not counted."""
        now = int(time.time())

        async def _high_voice_threshold(
            guild_id: int,
            key: str,
            default: object = None,
        ) -> object:
            if key == "metrics.min_voice_minutes":
                return 60  # 60 minutes minimum
            if key in ("metrics.min_game_minutes", "metrics.min_messages"):
                return 0
            return default if default is not None else []

        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=_high_voice_threshold,
        )
        metrics_service._activity_thresholds_cache.clear()

        # Record a quick 5-minute voice session (< 60 min threshold)
        await metrics_service.record_voice_join(
            guild_id=100,
            user_id=3,
            channel_id=10,
        )
        # Manually set the join time to 5 minutes ago
        session = metrics_service._voice_sessions[(100, 3)]
        session.joined_at = now - 300  # 5 minutes
        await metrics_service.record_voice_leave(guild_id=100, user_id=3)

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 3 not in result

    @pytest.mark.asyncio
    async def test_voice_above_threshold_included(
        self, metrics_service: MetricsService
    ) -> None:
        """Voice sessions meeting min_voice_minutes are counted."""
        now = int(time.time())

        async def _threshold_15(
            guild_id: int,
            key: str,
            default: object = None,
        ) -> object:
            if key == "metrics.min_voice_minutes":
                return 15  # 15 minutes minimum
            if key in ("metrics.min_game_minutes", "metrics.min_messages"):
                return 0
            return default if default is not None else []

        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=_threshold_15,
        )
        metrics_service._activity_thresholds_cache.clear()

        # Record a 20-minute voice session (> 15 min threshold)
        await metrics_service.record_voice_join(
            guild_id=100,
            user_id=4,
            channel_id=10,
        )
        session = metrics_service._voice_sessions[(100, 4)]
        session.joined_at = now - 1200  # 20 minutes ago
        await metrics_service.record_voice_leave(guild_id=100, user_id=4)

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 4 in result
        assert result[4]["voice_tier"] == "hardcore"

    @pytest.mark.asyncio
    async def test_zero_thresholds_count_everything(
        self, metrics_service: MetricsService
    ) -> None:
        """When thresholds are 0, any activity counts (default fixture behaviour)."""
        now = int(time.time())

        # Fixture already returns 0 for threshold keys — just confirm
        metrics_service._activity_thresholds_cache.clear()

        metrics_service.record_message(guild_id=100, user_id=5, channel_id=10)
        await metrics_service._flush_message_buffer()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )
        assert 5 in result
        assert result[5]["chat_tier"] == "hardcore"

    @pytest.mark.asyncio
    async def test_threshold_cache_respects_ttl(
        self, metrics_service: MetricsService
    ) -> None:
        """Threshold values are cached and only refreshed after TTL."""
        original_get_setting = cast(
            "AsyncMock",
            metrics_service._config_service.get_guild_setting,
        )
        call_counter = {"count": 0}

        async def _counting_get_setting(
            guild_id: int,
            key: str,
            default: object = None,
        ) -> object:
            call_counter["count"] += 1
            return await original_get_setting(guild_id, key, default)

        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=_counting_get_setting,
        )

        # Seed cache
        await metrics_service.get_activity_thresholds(guild_id=100)
        call_count = call_counter["count"]

        # Second call within TTL — should use cache
        await metrics_service.get_activity_thresholds(guild_id=100)
        assert call_counter["count"] == call_count

        # Force refresh bypasses cache
        await metrics_service.get_activity_thresholds(
            guild_id=100,
            force_refresh=True,
        )
        assert call_counter["count"] > call_count

    @pytest.mark.asyncio
    async def test_activity_chat_ignores_legacy_hourly_message_rows(
        self,
        metrics_service: MetricsService,
    ) -> None:
        """Cadence chat tiers should only count 3-minute message windows."""
        now = int(time.time())
        legacy_hour_bucket = now - (now % 3600)

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO message_counts "
                "(guild_id, user_id, hour_bucket, bucket_seconds, message_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (100, 4242, legacy_hour_bucket, 3600, 50),
            )
            await db.commit()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )

        assert 4242 not in result

    @pytest.mark.asyncio
    async def test_activity_chat_counts_three_minute_message_rows(
        self,
        metrics_service: MetricsService,
    ) -> None:
        """3-minute message rows should count as qualifying chat windows."""
        now = int(time.time())
        message_bucket = now - (now % 180)

        async with MetricsDatabase.get_connection() as db:
            await db.execute(
                "INSERT INTO message_counts "
                "(guild_id, user_id, hour_bucket, bucket_seconds, message_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (100, 5151, message_bucket, 180, 3),
            )
            await db.commit()

        result = await metrics_service.get_member_activity_buckets(
            guild_id=100,
            lookback_days=1,
            now_utc=now,
        )

        assert 5151 in result
        assert result[5151]["chat_tier"] == "hardcore"


class TestGuildMetricsAverages:
    """Tests for unique_users=0 handling in get_guild_metrics."""

    @pytest.mark.asyncio
    async def test_empty_guild_returns_zero_averages(
        self, metrics_service: MetricsService
    ) -> None:
        """When no activity exists, averages should be 0, not divide-by-zero."""
        result = await metrics_service.get_guild_metrics(guild_id=999, days=7)
        assert result["unique_users"] == 0
        assert result["avg_messages_per_user"] == 0.0
        assert result["avg_voice_per_user"] == 0


# ---------------------------------------------------------------------------
# Backfill voice state — self-mute / self-deaf filtering
# ---------------------------------------------------------------------------


class TestBackfillVoiceStateEligibility:
    """Verify that backfill_voice_state respects self-mute / self-deaf."""

    @staticmethod
    def _make_bot(members_by_channel: dict) -> MagicMock:
        """Build a minimal Bot mock with guilds / voice_channels / members.

        ``members_by_channel`` maps ``(guild_id, channel_id)`` to a list of
        ``(member_id, self_mute, self_deaf)`` tuples.
        """
        from collections import defaultdict

        guilds_map: dict[int, list] = defaultdict(list)
        for (guild_id, channel_id), member_specs in members_by_channel.items():
            vc = MagicMock()
            vc.id = channel_id
            members = []
            for mid, s_mute, s_deaf in member_specs:
                m = MagicMock()
                m.id = mid
                m.bot = False
                m.voice = MagicMock()
                m.voice.self_mute = s_mute
                m.voice.self_deaf = s_deaf
                members.append(m)
            vc.members = members
            guilds_map[guild_id].append(vc)

        guilds = []
        for gid, vcs in guilds_map.items():
            g = MagicMock()
            g.id = gid
            g.voice_channels = vcs
            guilds.append(g)

        bot = MagicMock()
        bot.guilds = guilds
        return bot

    @pytest.mark.asyncio
    async def test_backfill_skips_self_muted(
        self, metrics_service: MetricsService
    ) -> None:
        """Self-muted members should NOT get a backfilled session."""
        bot = self._make_bot(
            {(100, 10): [(1, True, False)]}  # self_mute=True
        )
        await metrics_service.backfill_voice_state(bot)
        assert (100, 1) not in metrics_service._voice_sessions

    @pytest.mark.asyncio
    async def test_backfill_skips_self_deafened(
        self, metrics_service: MetricsService
    ) -> None:
        """Self-deafened members should NOT get a backfilled session."""
        bot = self._make_bot(
            {(100, 10): [(2, False, True)]}  # self_deaf=True
        )
        await metrics_service.backfill_voice_state(bot)
        assert (100, 2) not in metrics_service._voice_sessions

    @pytest.mark.asyncio
    async def test_backfill_includes_eligible_member(
        self, metrics_service: MetricsService
    ) -> None:
        """An unmuted, undeafened member should get a backfilled session."""
        bot = self._make_bot({(100, 10): [(3, False, False)]})
        await metrics_service.backfill_voice_state(bot)
        assert (100, 3) in metrics_service._voice_sessions
        assert metrics_service._voice_sessions[(100, 3)].channel_id == 10

    @pytest.mark.asyncio
    async def test_backfill_mixed_members(
        self, metrics_service: MetricsService
    ) -> None:
        """Only eligible members are backfilled from a channel with a mix."""
        bot = self._make_bot(
            {
                (100, 10): [
                    (1, False, False),  # eligible
                    (2, True, False),  # muted — skip
                    (3, False, True),  # deafened — skip
                ],
            }
        )
        await metrics_service.backfill_voice_state(bot)
        assert (100, 1) in metrics_service._voice_sessions
        assert (100, 2) not in metrics_service._voice_sessions
        assert (100, 3) not in metrics_service._voice_sessions


# ---------------------------------------------------------------------------
# Backfill voice state — excluded-channel filtering (GDPR minimization)
# ---------------------------------------------------------------------------


class TestBackfillVoiceExcludedChannels:
    """Verify that backfill_voice_state honours excluded channel IDs."""

    @staticmethod
    def _make_bot(members_by_channel: dict) -> MagicMock:
        """Same helper as TestBackfillVoiceStateEligibility."""
        from collections import defaultdict as _defaultdict

        guilds_map: dict[int, list] = _defaultdict(list)
        for (guild_id, channel_id), member_specs in members_by_channel.items():
            vc = MagicMock()
            vc.id = channel_id
            members = []
            for mid, s_mute, s_deaf in member_specs:
                m = MagicMock()
                m.id = mid
                m.bot = False
                m.voice = MagicMock()
                m.voice.self_mute = s_mute
                m.voice.self_deaf = s_deaf
                members.append(m)
            vc.members = members
            guilds_map[guild_id].append(vc)

        guilds = []
        for gid, vcs in guilds_map.items():
            g = MagicMock()
            g.id = gid
            g.voice_channels = vcs
            guilds.append(g)

        bot = MagicMock()
        bot.guilds = guilds
        return bot

    @pytest.mark.asyncio
    async def test_backfill_skips_excluded_voice_channel(
        self, metrics_service: MetricsService
    ) -> None:
        """Members in an excluded channel should NOT get a backfilled session."""
        excluded_channel_id = 10
        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=lambda gid, key, default=None: (
                [excluded_channel_id]
                if key == "metrics.excluded_channel_ids"
                else (0 if "min_" in key else default if default is not None else [])
            )
        )
        # Invalidate cache so fresh config is read
        metrics_service._excluded_channels_cache.clear()

        bot = self._make_bot({(100, excluded_channel_id): [(1, False, False)]})
        await metrics_service.backfill_voice_state(bot)
        assert (100, 1) not in metrics_service._voice_sessions

    @pytest.mark.asyncio
    async def test_backfill_includes_non_excluded_channel(
        self, metrics_service: MetricsService
    ) -> None:
        """Members in a non-excluded channel should get a session."""
        excluded_channel_id = 10
        normal_channel_id = 20
        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=lambda gid, key, default=None: (
                [excluded_channel_id]
                if key == "metrics.excluded_channel_ids"
                else (0 if "min_" in key else default if default is not None else [])
            )
        )
        metrics_service._excluded_channels_cache.clear()

        bot = self._make_bot({(100, normal_channel_id): [(2, False, False)]})
        await metrics_service.backfill_voice_state(bot)
        assert (100, 2) in metrics_service._voice_sessions
        assert metrics_service._voice_sessions[(100, 2)].channel_id == normal_channel_id

    @pytest.mark.asyncio
    async def test_backfill_mixed_excluded_and_normal_channels(
        self, metrics_service: MetricsService
    ) -> None:
        """Only non-excluded channels produce backfilled sessions."""
        excluded_id = 10
        normal_id = 20
        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=lambda gid, key, default=None: (
                [excluded_id]
                if key == "metrics.excluded_channel_ids"
                else (0 if "min_" in key else default if default is not None else [])
            )
        )
        metrics_service._excluded_channels_cache.clear()

        bot = self._make_bot(
            {
                (100, excluded_id): [(1, False, False)],  # excluded
                (100, normal_id): [(2, False, False)],  # allowed
            }
        )
        await metrics_service.backfill_voice_state(bot)
        assert (100, 1) not in metrics_service._voice_sessions
        assert (100, 2) in metrics_service._voice_sessions


# ---------------------------------------------------------------------------
# Backfill game state — excluded-channel filtering (GDPR minimization)
# ---------------------------------------------------------------------------


class TestBackfillGameExcludedChannels:
    """Verify that backfill_game_state skips members in excluded voice channels."""

    @staticmethod
    def _make_bot(
        members: list[tuple[int, int, str | None, int | None]],
    ) -> MagicMock:
        """Build a Bot mock for game backfill.

        Each entry is ``(guild_id, member_id, game_name, voice_channel_id)``.
        ``game_name=None`` means no playing activity.
        ``voice_channel_id=None`` means not in a voice channel.
        """
        import discord

        guilds_map: dict[int, list[MagicMock]] = {}
        for guild_id, member_id, game_name, vc_id in members:
            m = MagicMock()
            m.id = member_id
            m.bot = False
            if vc_id is not None:
                m.voice = MagicMock()
                m.voice.channel = MagicMock()
                m.voice.channel.id = vc_id
            else:
                m.voice = None
            if game_name is not None:
                activity = MagicMock()
                activity.type = discord.ActivityType.playing
                activity.name = game_name
                m.activities = [activity]
            else:
                m.activities = []
            guilds_map.setdefault(guild_id, []).append(m)

        guilds = []
        for gid, mems in guilds_map.items():
            g = MagicMock()
            g.id = gid
            g.members = mems
            g.voice_channels = []
            guilds.append(g)

        bot = MagicMock()
        bot.guilds = guilds
        return bot

    @pytest.mark.asyncio
    async def test_game_backfill_skips_excluded_channel_member(
        self, metrics_service: MetricsService
    ) -> None:
        """A member playing a game in an excluded voice channel is NOT backfilled."""
        excluded_id = 10
        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=lambda gid, key, default=None: (
                [excluded_id]
                if key == "metrics.excluded_channel_ids"
                else (0 if "min_" in key else default if default is not None else [])
            )
        )
        metrics_service._excluded_channels_cache.clear()

        bot = self._make_bot([(100, 1, "Star Citizen", excluded_id)])
        await metrics_service.backfill_game_state(bot)
        assert (100, 1) not in metrics_service._game_sessions

    @pytest.mark.asyncio
    async def test_game_backfill_includes_non_excluded_member(
        self, metrics_service: MetricsService
    ) -> None:
        """A member playing in a normal voice channel IS backfilled."""
        excluded_id = 10
        normal_id = 20
        metrics_service._config_service.get_guild_setting = AsyncMock(
            side_effect=lambda gid, key, default=None: (
                [excluded_id]
                if key == "metrics.excluded_channel_ids"
                else (0 if "min_" in key else default if default is not None else [])
            )
        )
        metrics_service._excluded_channels_cache.clear()

        bot = self._make_bot([(100, 2, "Star Citizen", normal_id)])
        await metrics_service.backfill_game_state(bot)
        assert (100, 2) in metrics_service._game_sessions

    @pytest.mark.asyncio
    async def test_game_backfill_includes_member_not_in_voice(
        self, metrics_service: MetricsService
    ) -> None:
        """A member playing a game but NOT in any voice channel IS backfilled."""
        metrics_service._excluded_channels_cache.clear()

        bot = self._make_bot([(100, 3, "Star Citizen", None)])
        await metrics_service.backfill_game_state(bot)
        assert (100, 3) in metrics_service._game_sessions
