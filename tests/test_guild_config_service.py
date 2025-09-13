"""
Tests for GuildConfigService.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from services.db.database import Database
from services.guild_config_service import GuildConfigService


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    """Create a temporary database for testing."""
    # Reset database state
    orig_path = Database._db_path
    Database._initialized = False

    # Create temp database file
    db_file = tmp_path / "test_guild_config.db"
    await Database.initialize(str(db_file))

    yield str(db_file)

    # Cleanup - reset to original state
    Database._db_path = orig_path
    Database._initialized = False


@pytest_asyncio.fixture
async def config_service():
    """Create a GuildConfigService instance for testing."""
    return GuildConfigService(ttl_seconds=1)  # Short TTL for testing


@pytest_asyncio.fixture
async def populated_db(temp_db):
    """Create a database with some test data."""
    async with Database.get_connection() as db:
        # Insert test guild settings
        await db.execute(
            "INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (123456789, "join_to_create_channel_ids", json.dumps([111, 222, 333])),
        )
        await db.execute(
            "INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (123456789, "voice_category_id", "999888777"),
        )
        await db.execute(
            "INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (987654321, "join_to_create_channel_ids", json.dumps([444, 555])),
        )
        await db.commit()
    return temp_db


class TestGuildConfigService:
    """Tests for GuildConfigService."""

    @pytest.mark.asyncio
    async def test_service_initialization(self, temp_db, config_service):
        """Test that service initializes correctly."""
        assert config_service.ttl_seconds == 1
        assert len(config_service._cache) == 0
        assert len(config_service._write_locks) == 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_setting(self, populated_db, config_service):
        """Test getting a setting that doesn't exist returns None."""
        result = await config_service.get(123456789, "nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_existing_setting(self, populated_db, config_service):
        """Test getting an existing setting returns correct value."""
        result = await config_service.get(123456789, "join_to_create_channel_ids")
        assert result == [111, 222, 333]

    @pytest.mark.asyncio
    async def test_get_with_parser(self, populated_db, config_service):
        """Test getting a setting with a custom parser."""
        result = await config_service.get(123456789, "voice_category_id", parser=int)
        assert result == 999888777
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_set_and_get_setting(self, populated_db, config_service):
        """Test setting and getting a new value."""
        guild_id = 111222333
        key = "test_setting"
        value = {"test": "data", "number": 42}

        # Set the value
        await config_service.set(guild_id, key, value)

        # Get it back
        result = await config_service.get(guild_id, key)
        assert result == value

    @pytest.mark.asyncio
    async def test_cache_behavior(self, populated_db, config_service):
        """Test that caching works correctly."""
        guild_id = 123456789
        key = "join_to_create_channel_ids"

        # First access should hit the database
        result1 = await config_service.get(guild_id, key)
        assert result1 == [111, 222, 333]

        # Should be cached now
        cache_key = (guild_id, key)
        assert cache_key in config_service._cache

        # Modify the database directly
        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE guild_settings SET value = ? WHERE guild_id = ? AND key = ?",
                (json.dumps([777, 888]), guild_id, key),
            )
            await db.commit()

        # Should still get cached value
        result2 = await config_service.get(guild_id, key)
        assert result2 == [111, 222, 333]  # Still cached

        # Wait for cache to expire
        await asyncio.sleep(1.1)

        # Now should get updated value from database
        result3 = await config_service.get(guild_id, key)
        assert result3 == [777, 888]

    @pytest.mark.asyncio
    async def test_set_invalidates_cache(self, populated_db, config_service):
        """Test that setting a value invalidates the cache."""
        guild_id = 123456789
        key = "join_to_create_channel_ids"

        # Get initial value (caches it)
        result1 = await config_service.get(guild_id, key)
        assert result1 == [111, 222, 333]

        # Set new value
        new_value = [999, 888, 777]
        await config_service.set(guild_id, key, new_value)

        # Should immediately return new value
        result2 = await config_service.get(guild_id, key)
        assert result2 == new_value

    @pytest.mark.asyncio
    async def test_get_join_to_create_channels(self, populated_db, config_service):
        """Test the specialized JTC channels getter."""
        result = await config_service.get_join_to_create_channels(123456789)
        assert result == [111, 222, 333]

        # Test empty guild
        result_empty = await config_service.get_join_to_create_channels(999999999)
        assert result_empty == []

    @pytest.mark.asyncio
    async def test_set_join_to_create_channels(self, populated_db, config_service):
        """Test the specialized JTC channels setter."""
        guild_id = 555666777
        channels = [123, 456, 789]

        await config_service.set_join_to_create_channels(guild_id, channels)
        result = await config_service.get_join_to_create_channels(guild_id)
        assert result == channels

    @pytest.mark.asyncio
    async def test_get_voice_category_id(self, populated_db, config_service):
        """Test the specialized voice category getter."""
        result = await config_service.get_voice_category_id(123456789)
        assert result == 999888777

        # Test nonexistent guild
        result_none = await config_service.get_voice_category_id(999999999)
        assert result_none is None

    @pytest.mark.asyncio
    async def test_set_voice_category_id(self, populated_db, config_service):
        """Test the specialized voice category setter."""
        guild_id = 777888999
        category_id = 123456

        await config_service.set_voice_category_id(guild_id, category_id)
        result = await config_service.get_voice_category_id(guild_id)
        assert result == category_id

        # Test setting to None
        await config_service.set_voice_category_id(guild_id, None)
        result_none = await config_service.get_voice_category_id(guild_id)
        assert result_none is None

    @pytest.mark.asyncio
    async def test_race_safe_writes(self, populated_db, config_service):
        """Test that concurrent writes to the same key are serialized."""
        guild_id = 123456789
        key = "test_concurrent"

        # Simulate concurrent writes
        async def write_value(value):
            await config_service.set(guild_id, key, value)

        tasks = [write_value(f"value_{i}") for i in range(10)]

        await asyncio.gather(*tasks)

        # Should have one of the values (exact value depends on execution order)
        result = await config_service.get(guild_id, key)
        assert isinstance(result, str)
        assert result.startswith("value_")

    @pytest.mark.asyncio
    async def test_clear_cache(self, populated_db, config_service):
        """Test cache clearing functionality."""
        guild_id1 = 123456789
        guild_id2 = 987654321
        key = "join_to_create_channel_ids"

        # Load values into cache
        await config_service.get(guild_id1, key)
        await config_service.get(guild_id2, key)

        assert len(config_service._cache) == 2

        # Clear specific guild cache
        await config_service.clear_cache(guild_id1)
        assert len(config_service._cache) == 1
        assert (guild_id1, key) not in config_service._cache
        assert (guild_id2, key) in config_service._cache

        # Clear all cache
        await config_service.clear_cache()
        assert len(config_service._cache) == 0

    @pytest.mark.asyncio
    async def test_maybe_migrate_legacy_settings_no_guilds(
        self, populated_db, config_service
    ):
        """Test migration with no guilds."""
        mock_bot = MagicMock()
        mock_bot.guilds = []

        # Should log warning but not crash
        await config_service.maybe_migrate_legacy_settings(mock_bot)
        # No assertion needed, just ensure it doesn't raise

    @pytest.mark.asyncio
    async def test_maybe_migrate_legacy_settings_multiple_guilds(
        self, populated_db, config_service
    ):
        """Test migration with multiple guilds."""
        # Create legacy settings
        async with Database.get_connection() as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("join_to_create_channel_ids", json.dumps([111, 222])),
            )
            await db.commit()

        mock_guild1 = MagicMock()
        mock_guild1.id = 111
        mock_guild1.name = "Guild 1"

        mock_guild2 = MagicMock()
        mock_guild2.id = 222
        mock_guild2.name = "Guild 2"

        mock_bot = MagicMock()
        mock_bot.guilds = [mock_guild1, mock_guild2]

        # Should log warning and not migrate
        await config_service.maybe_migrate_legacy_settings(mock_bot)

        # Check that no migration occurred
        result = await config_service.get_join_to_create_channels(111)
        assert result == []

    @pytest.mark.asyncio
    async def test_maybe_migrate_legacy_settings_single_guild(
        self, temp_db, config_service
    ):
        """Test successful migration with single guild."""
        # Create legacy settings
        async with Database.get_connection() as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("join_to_create_channel_ids", json.dumps([111, 222])),
            )
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("voice_category_id", "999"),
            )
            await db.commit()

        mock_guild = MagicMock()
        mock_guild.id = 555
        mock_guild.name = "Test Guild"

        mock_bot = MagicMock()
        mock_bot.guilds = [mock_guild]

        # Should migrate successfully
        await config_service.maybe_migrate_legacy_settings(mock_bot)

        # Check that migration occurred
        jtc_result = await config_service.get_join_to_create_channels(555)
        assert jtc_result == [111, 222]

        category_result = await config_service.get_voice_category_id(555)
        assert category_result == 999

    @pytest.mark.asyncio
    async def test_maybe_migrate_legacy_settings_existing_guild_settings(
        self, populated_db, config_service
    ):
        """Test that migration is skipped when guild settings already exist."""
        # Guild settings already exist in populated_db fixture

        # Create legacy settings
        async with Database.get_connection() as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("join_to_create_channel_ids", json.dumps([999, 888])),
            )
            await db.commit()

        mock_guild = MagicMock()
        mock_guild.id = 777
        mock_guild.name = "Test Guild"

        mock_bot = MagicMock()
        mock_bot.guilds = [mock_guild]

        # Should skip migration
        await config_service.maybe_migrate_legacy_settings(mock_bot)

        # Check that existing settings are unchanged and no new settings created
        result = await config_service.get_join_to_create_channels(777)
        assert result == []  # No settings for guild 777
