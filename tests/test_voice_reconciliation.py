"""Tests for voice channel reconciliation on startup."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from services.db.database import Database
from services.voice_service import VoiceService


class TestVoiceReconciliation:
    """Test voice channel reconciliation functionality."""

    @pytest.fixture
    def mock_config_service(self):
        """Mock ConfigService instance."""
        config_service = AsyncMock()
        # Fix the startup delay setting that's causing issues
        config_service.get_global_setting.return_value = (
            2000  # Return actual value, not mock
        )
        return config_service

    @pytest.fixture
    def mock_bot(self):
        """Mock Discord bot instance."""
        bot = AsyncMock()
        bot.wait_until_ready = AsyncMock()

        # Make get_channel a regular method that returns synchronously
        bot.get_channel = MagicMock()  # Regular Mock, not AsyncMock
        bot.fetch_channel = AsyncMock()  # Keep this async
        bot.get_guild = MagicMock()  # Also make this regular to avoid coroutine issues

        # Mock guild
        guild = MagicMock()
        guild.id = 12345
        guild.name = "Test Guild"
        bot.guilds = [guild]

        # Fix AsyncMock behavior - return actual values instead of coroutines
        bot.get_channel.return_value = None  # By default, return None
        bot.fetch_channel = AsyncMock()  # This will be configured per test

        return bot

    @pytest_asyncio.fixture
    async def voice_service(self, mock_config_service, mock_bot):
        """Create VoiceService instance with mocked dependencies."""
        service = VoiceService(mock_config_service, mock_bot)

        # Mock initialization to avoid actual database setup and startup tasks
        with (
            patch.object(service, "_ensure_voice_tables"),
            patch.object(service, "_cleanup_orphaned_jtc_data"),
            patch.object(service, "_load_managed_channels"),
            patch("asyncio.create_task"),
        ):  # Prevent startup tasks from running
            await service._initialize_impl()

        yield service
        # Properly shut down the service after test
        await service.shutdown()

    @pytest.mark.asyncio
    async def test_reconcile_all_guilds_on_ready(self, voice_service, mock_bot):
        """Test reconcile_all_guilds_on_ready method."""

        # Mock database data - existing channels
        mock_channels = [
            (
                12345,
                111,
                100,
                201,
                1234567890,
            ),  # guild_id, voice_channel_id, owner_id, jtc_channel_id, created_at
            (12345, 222, 200, 202, 1234567891),  # Another channel
            (12345, 333, 300, 203, 1234567892),  # Channel that doesn't exist
        ]

        with patch.object(Database, "get_connection") as mock_db_conn:
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            mock_cursor.fetchall = AsyncMock(return_value=mock_channels)
            mock_db.execute = AsyncMock(return_value=mock_cursor)
            mock_db_conn.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock individual channel reconciliation
            with patch.object(
                voice_service, "_reconcile_single_channel"
            ) as mock_reconcile:
                await voice_service.reconcile_all_guilds_on_ready()

                # Verify each channel was reconciled
                assert mock_reconcile.call_count == 3
                mock_reconcile.assert_any_call(12345, 111, 100, 201, 1234567890)
                mock_reconcile.assert_any_call(12345, 222, 200, 202, 1234567891)
                mock_reconcile.assert_any_call(12345, 333, 300, 203, 1234567892)

    @pytest.mark.asyncio
    async def test_reconcile_single_channel_nonexistent(self, voice_service, mock_bot):
        """Test reconciling a channel that doesn't exist - should remove from DB."""

        # Mock bot returning None for both get_channel and fetch_channel
        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel.side_effect = discord.NotFound(
            MagicMock(), "Channel not found"
        )

        # Mock the config service call that happens later
        voice_service.config_service.get_global_setting = AsyncMock(
            return_value="delayed"
        )

        # Mock the cleanup_by_channel_id method to verify it's called
        with patch.object(voice_service, "cleanup_by_channel_id") as mock_cleanup:
            await voice_service._reconcile_single_channel(
                12345, 111, 100, 201, 1234567890
            )

            # Verify cleanup was called with the correct channel ID
            mock_cleanup.assert_called_once_with(111)

    @pytest.mark.asyncio
    async def test_reconcile_single_channel_with_members(self, voice_service, mock_bot):
        """Test reconciling a channel with members - should rehydrate."""

        # Mock channel with members
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.id = 111
        mock_channel.name = "Test Channel"
        mock_channel.guild.id = 12345
        mock_channel.members = [MagicMock(), MagicMock()]  # Has 2 members

        mock_bot.get_channel.return_value = mock_channel

        # Mock config service for startup_cleanup_mode
        voice_service.config_service.get_global_setting.return_value = "delayed"

        with (
            patch.object(
                voice_service, "_should_keep_channel_active", return_value=True
            ) as mock_should_keep,
            patch.object(
                voice_service, "_rehydrate_channel_management"
            ) as mock_rehydrate,
        ):
            await voice_service._reconcile_single_channel(
                12345, 111, 100, 201, 1234567890
            )

            # Verify channel was checked for activity
            mock_should_keep.assert_called_once_with(mock_channel, 100)

            # Verify channel was added to managed channels
            assert 111 in voice_service.managed_voice_channels

            # Verify rehydration was called
            mock_rehydrate.assert_called_once_with(mock_channel, 100, 201, 12345)

    @pytest.mark.asyncio
    async def test_reconcile_single_channel_empty(self, voice_service, mock_bot):
        """Test reconciling an empty channel - should schedule cleanup."""

        # Mock empty channel
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.id = 111
        mock_channel.name = "Test Channel"
        mock_channel.guild.id = 12345
        mock_channel.members = []  # Empty

        # Set the return value normally since get_channel is now a regular Mock
        mock_bot.get_channel.return_value = mock_channel

        # Mock config service for startup_cleanup_mode (delayed by default)
        voice_service.config_service.get_global_setting.return_value = "delayed"

        with (
            patch.object(
                voice_service, "_should_keep_channel_active", return_value=False
            ) as mock_should_keep,
            patch.object(
                voice_service, "_schedule_channel_cleanup"
            ) as mock_schedule_cleanup,
        ):
            await voice_service._reconcile_single_channel(
                12345, 111, 100, 201, 1234567890
            )

            # Verify channel was checked for activity
            mock_should_keep.assert_called_once_with(mock_channel, 100)

            # Verify cleanup was scheduled
            mock_schedule_cleanup.assert_called_once_with(111)

    @pytest.mark.asyncio
    async def test_should_keep_channel_active_with_members(self, voice_service):
        """Test that channels with members are kept active."""

        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.members = [MagicMock(), MagicMock()]

        result = await voice_service._should_keep_channel_active(mock_channel, 100)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_keep_channel_active_owner_connected(self, voice_service):
        """Test that empty channels with owner connected are kept active."""

        # Mock empty channel but owner is connected
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.id = 111
        mock_channel.members = []

        mock_guild = MagicMock()
        mock_channel.guild = mock_guild

        mock_owner = MagicMock()
        mock_owner.voice.channel.id = 111  # Owner is in this channel
        mock_guild.get_member.return_value = mock_owner

        result = await voice_service._should_keep_channel_active(mock_channel, 100)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_keep_channel_active_empty_no_owner(self, voice_service):
        """Test that empty channels without owner are not kept active."""

        # Mock empty channel with no owner connected
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.id = 111
        mock_channel.members = []

        mock_guild = MagicMock()
        mock_channel.guild = mock_guild
        mock_guild.get_member.return_value = None  # Owner not found

        result = await voice_service._should_keep_channel_active(mock_channel, 100)

        assert result is False

    @pytest.mark.asyncio
    async def test_rehydrate_channel_management(self, voice_service, mock_bot):
        """Test channel management rehydration."""

        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.id = 111
        mock_channel.name = "Test Channel"

        # Mock the guild properly to avoid the get_member error
        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock()  # Return a mock member
        mock_channel.guild = mock_guild

        # Set up the bot's get_guild to return the mock guild
        mock_bot.get_guild.return_value = mock_guild

        # Mock the enforce_permission_changes import and call
        with patch(
            "helpers.voice_permissions.enforce_permission_changes"
        ) as mock_enforce:
            mock_enforce.return_value = AsyncMock()  # Make it async
            await voice_service._rehydrate_channel_management(
                mock_channel, 100, 201, 12345
            )

            # Verify permissions were enforced with correct signature:
            # (channel, bot, user_id, guild_id, jtc_channel_id)
            mock_enforce.assert_called_once_with(
                mock_channel, mock_bot, 100, 12345, 201
            )
