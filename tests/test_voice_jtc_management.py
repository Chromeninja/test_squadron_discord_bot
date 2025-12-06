"""
Tests for JTC channel management functionality.

Tests adding, removing, and automatic cleanup of JTC channels.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


class MockVoiceChannel:
    """Mock Discord voice channel."""

    def __init__(self, channel_id: int, name: str = "test-channel", members=None):
        self.id = channel_id
        self.name = name
        self.members = members or []
        self.guild = MagicMock()
        self.guild.id = 12345
        self.guild.get_member = MagicMock(return_value=None)
        self.category = MagicMock()
        self.category.id = 77777
        self.category.name = "Voice Category"
        self.category.create_voice_channel = AsyncMock()
        self.delete = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockBot:
    """Mock Discord bot."""

    def __init__(self):
        self.channels_map = {}
        self.user = MagicMock()
        self.user.id = 999999

    def add_channel(self, channel: MockVoiceChannel):
        """Add a channel to the bot."""
        self.channels_map[channel.id] = channel

    def get_channel(self, channel_id: int) -> MockVoiceChannel | None:
        """Get a channel by ID."""
        return self.channels_map.get(channel_id)


class TestJTCManagement:
    """Tests for JTC channel management functionality."""

    @pytest_asyncio.fixture
    async def temp_db(self, tmp_path):
        """Initialize Database to a temporary file."""
        db_path = tmp_path / "test_jtc.db"

        # Save original state
        original_db_path = Database._db_path
        was_initialized = Database._initialized

        # Initialize test database
        Database._initialized = False
        Database._db_path = str(db_path)
        await Database.initialize(str(db_path))

        yield str(db_path)

        # Restore original state
        Database._initialized = was_initialized
        Database._db_path = original_db_path

    @pytest_asyncio.fixture
    async def voice_service_with_bot(self, temp_db):
        """Create voice service with mock bot for testing."""
        config_service = ConfigService()
        await config_service.initialize()

        mock_bot = MockBot()
        voice_service = VoiceService(config_service, bot=mock_bot)  # type: ignore[arg-type]
        await voice_service.initialize()

        yield voice_service, mock_bot

        await voice_service.shutdown()
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_add_jtc_channel_success(self, voice_service_with_bot):
        """Test successful addition of JTC channel."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        new_channel_id = 88888

        # Verify channel not in config initially
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert new_channel_id not in jtc_channels

        # Add channel
        success, error = await voice_service.add_jtc_channel_to_config(
            guild_id, new_channel_id
        )

        assert success is True
        assert error is None

        # Verify channel is now in config
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert new_channel_id in jtc_channels

    @pytest.mark.asyncio
    async def test_add_jtc_channel_duplicate(self, voice_service_with_bot):
        """Test error when adding duplicate JTC channel."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        channel_id = 88889

        # Add channel first time
        await voice_service.config_service.add_guild_jtc_channel(guild_id, channel_id)

        # Try to add again
        success, error = await voice_service.add_jtc_channel_to_config(
            guild_id, channel_id
        )

        assert success is False
        assert error is not None
        assert "already configured" in error.lower()

    @pytest.mark.asyncio
    async def test_remove_jtc_channel_success(self, voice_service_with_bot):
        """Test successful removal of JTC channel."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        channel_id = 88890

        # Add channel first
        await voice_service.config_service.add_guild_jtc_channel(guild_id, channel_id)

        # Verify it's in config
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert channel_id in jtc_channels

        # Remove channel
        result = await voice_service.remove_jtc_channel_from_config(
            guild_id, channel_id, cleanup_managed=False
        )

        assert result["success"] is True
        assert result["error"] is None

        # Verify it's removed from config
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert channel_id not in jtc_channels

    @pytest.mark.asyncio
    async def test_remove_jtc_channel_not_found(self, voice_service_with_bot):
        """Test error when removing non-existent JTC channel."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        channel_id = 88891

        # Try to remove channel that doesn't exist
        result = await voice_service.remove_jtc_channel_from_config(
            guild_id, channel_id, cleanup_managed=False
        )

        assert result["success"] is False
        assert result["error"] is not None
        assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_jtc_deletion_triggers_cleanup(self, voice_service_with_bot):
        """Test that JTC channel deletion triggers automatic cleanup."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        jtc_channel_id = 88892

        # Add JTC channel to config
        await voice_service.config_service.add_guild_jtc_channel(
            guild_id, jtc_channel_id
        )

        # Add a managed channel belonging to this JTC
        managed_channel_id = 99992
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    guild_id,
                    jtc_channel_id,
                    11111,
                    managed_channel_id,
                    1234567890,
                    1234567890,
                    1,
                ),
            )
            await db.commit()

        # Simulate JTC channel deletion
        await voice_service.handle_channel_deleted(guild_id, jtc_channel_id)

        # Verify JTC channel is removed from config
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert jtc_channel_id not in jtc_channels

        # Note: voice_channels table is NOT purged by purge_stale_jtc_data
        # (that only purges settings/permissions tables), so we don't check that here
        # The managed channel cleanup happens via cleanup_stale_jtc_managed_channels which marks as inactive

    @pytest.mark.asyncio
    async def test_managed_channel_deletion_no_jtc_removal(
        self, voice_service_with_bot
    ):
        """Test that managed channel deletion doesn't affect JTC config."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        jtc_channel_id = 88893
        managed_channel_id = 99993

        # Add JTC channel to config
        await voice_service.config_service.add_guild_jtc_channel(
            guild_id, jtc_channel_id
        )

        # Add a managed channel
        voice_service.managed_voice_channels.add(managed_channel_id)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    guild_id,
                    jtc_channel_id,
                    11111,
                    managed_channel_id,
                    1234567890,
                    1234567890,
                    1,
                ),
            )
            await db.commit()

        # Simulate managed channel deletion
        await voice_service.handle_channel_deleted(guild_id, managed_channel_id)

        # Verify JTC channel is still in config
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert jtc_channel_id in jtc_channels

        # Verify managed channel is cleaned up
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (managed_channel_id,),
            )
            count = await cursor.fetchone()
            assert count is not None
            assert count[0] == 0

    @pytest.mark.asyncio
    async def test_validate_jtc_permissions(self, voice_service_with_bot):
        """Test JTC permission validation."""
        voice_service, _mock_bot = voice_service_with_bot

        # Create a valid category
        category = MagicMock()
        category.guild = MagicMock()
        category.guild.get_member = MagicMock(return_value=MagicMock())

        # Create mock permissions
        mock_perms = MagicMock()
        mock_perms.manage_channels = True

        # Mock the permissions_for method
        category.permissions_for = MagicMock(return_value=mock_perms)

        # Validate permissions
        can_create, error = await voice_service._validate_jtc_permissions(category)

        assert can_create is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_jtc_permissions_missing_manage_channels(
        self, voice_service_with_bot
    ):
        """Test permission validation fails when bot lacks manage_channels."""
        voice_service, _mock_bot = voice_service_with_bot

        # Create category
        category = MagicMock()
        category.guild = MagicMock()
        category.guild.get_member = MagicMock(return_value=MagicMock())
        category.name = "Test Category"

        # Create mock permissions without manage_channels
        mock_perms = MagicMock()
        mock_perms.manage_channels = False

        category.permissions_for = MagicMock(return_value=mock_perms)

        # Validate permissions
        can_create, error = await voice_service._validate_jtc_permissions(category)

        assert can_create is False
        assert error is not None
        assert "Manage Channels" in error

    @pytest.mark.asyncio
    async def test_create_jtc_channel_success(self, voice_service_with_bot):
        """Test successful JTC channel creation."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345

        # Create category with proper mocking
        category = MagicMock()
        category.guild = MagicMock()
        category.guild.id = guild_id
        category.guild.get_member = MagicMock(
            return_value=MagicMock()
        )  # Bot member exists

        # Mock permissions
        mock_perms = MagicMock()
        mock_perms.manage_channels = True
        category.permissions_for = MagicMock(return_value=mock_perms)

        # Mock channel creation
        new_channel = MockVoiceChannel(88894, "New JTC Channel")
        category.create_voice_channel = AsyncMock(return_value=new_channel)

        # Create channel
        channel, error = await voice_service.create_jtc_channel(
            guild_id, category, "New JTC Channel"
        )

        assert channel is not None
        assert channel.id == 88894
        assert error is None

        # Verify create was called
        category.create_voice_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_jtc_channels_per_guild(self, voice_service_with_bot):
        """Test multiple JTC channels can be configured per guild."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        jtc_ids = [88895, 88896, 88897]

        # Add multiple JTC channels
        for jtc_id in jtc_ids:
            success, error = await voice_service.add_jtc_channel_to_config(
                guild_id, jtc_id
            )
            assert success is True
            assert error is None

        # Verify all are in config
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        for jtc_id in jtc_ids:
            assert jtc_id in jtc_channels

        # Remove middle one
        result = await voice_service.remove_jtc_channel_from_config(
            guild_id, jtc_ids[1], cleanup_managed=False
        )
        assert result["success"] is True

        # Verify correct channels remain
        jtc_channels = await voice_service.config_service.get_guild_jtc_channels(
            guild_id
        )
        assert jtc_ids[0] in jtc_channels
        assert jtc_ids[1] not in jtc_channels
        assert jtc_ids[2] in jtc_channels

    @pytest.mark.asyncio
    async def test_cleanup_only_stale_jtc_data(self, voice_service_with_bot):
        """Test that removal only cleans up data for the removed JTC, not others."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        jtc1_id = 88898
        jtc2_id = 88899

        # Add both JTC channels
        await voice_service.config_service.add_guild_jtc_channel(guild_id, jtc1_id)
        await voice_service.config_service.add_guild_jtc_channel(guild_id, jtc2_id)

        # Add managed channels for both JTCs
        async with Database.get_connection() as db:
            for i, jtc_id in enumerate([jtc1_id, jtc2_id]):
                channel_id = 99994 + i
                await db.execute(
                    """
                    INSERT INTO voice_channels
                    (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        guild_id,
                        jtc_id,
                        11111 + i,
                        channel_id,
                        1234567890,
                        1234567890,
                        1,
                    ),
                )
            await db.commit()

        # Remove first JTC
        result = await voice_service.remove_jtc_channel_from_config(
            guild_id, jtc1_id, cleanup_managed=True
        )
        assert result["success"] is True

        # Verify second JTC's data is still intact
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE jtc_channel_id = ? AND is_active = 1",
                (jtc2_id,),
            )
            count = await cursor.fetchone()
            assert count is not None
            assert count[0] == 1  # Second JTC's channel should still be there

    @pytest.mark.asyncio
    async def test_remove_jtc_with_cleanup_stats(self, voice_service_with_bot):
        """Test removal returns correct cleanup statistics."""
        voice_service, _mock_bot = voice_service_with_bot

        guild_id = 12345
        jtc_channel_id = 88900

        # Add JTC channel
        await voice_service.config_service.add_guild_jtc_channel(
            guild_id, jtc_channel_id
        )

        # Add settings for the JTC channel
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO channel_settings
                (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (guild_id, jtc_channel_id, 55555, "Test Channel", 5, 0),
            )
            await db.commit()

        # Remove JTC and verify cleanup
        result = await voice_service.remove_jtc_channel_from_config(
            guild_id, jtc_channel_id, cleanup_managed=False
        )

        assert result["success"] is True
        assert result["db_purge"] is not None
        assert "channel_settings" in result["db_purge"]
