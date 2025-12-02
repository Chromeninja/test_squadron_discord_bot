"""
Tests for voice channel cleanup functionality.

Tests the new immediate cleanup when channels become empty and startup reconciliation.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


class MockVoiceChannel:
    """Mock Discord voice channel."""

    def __init__(
        self, channel_id: int, name: str = "test-channel", members: list | None = None
    ):
        self.id = channel_id
        self.name = name
        self.members = members or []
        self.guild = MagicMock()
        self.guild.id = 12345

    async def delete(self, reason: str | None = None):
        """Mock channel deletion."""
        pass


class MockBot:
    """Mock Discord bot."""

    def __init__(self):
        self._channels = {}
        self.guilds = []  # Add missing guilds attribute

    async def wait_until_ready(self):
        """Mock wait_until_ready method."""
        pass

    def get_channel(self, channel_id: int):
        """Get mock channel by ID."""
        return self._channels.get(channel_id)

    def add_channel(self, channel: MockVoiceChannel):
        """Add mock channel."""
        self._channels[channel.id] = channel

    def remove_channel(self, channel_id: int):
        """Remove mock channel."""
        self._channels.pop(channel_id, None)


class TestVoiceCleanup:
    """Tests for voice channel cleanup functionality."""

    @pytest_asyncio.fixture
    async def voice_service_with_bot(self, temp_db):
        """Create voice service with mock bot for testing."""
        config_service = ConfigService()
        await config_service.initialize()

        mock_bot = MockBot()
        voice_service = VoiceService(config_service, bot=mock_bot)
        await voice_service.initialize()

        yield voice_service, mock_bot

        await voice_service.shutdown()
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_immediate_cleanup_when_empty(self, voice_service_with_bot):
        """Test immediate cleanup when last member leaves a channel."""
        voice_service, mock_bot = voice_service_with_bot

        # Create and set up a channel
        channel = MockVoiceChannel(channel_id=12345, members=[])  # Empty channel
        mock_bot.add_channel(channel)

        # Add to managed channels and database
        voice_service.managed_voice_channels.add(channel.id)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Mock member leaving
        mock_member = MagicMock()
        mock_member.display_name = "TestUser"

        with patch.object(channel, "delete", new_callable=AsyncMock) as mock_delete:
            await voice_service._handle_channel_left(channel, mock_member)

            # Verify channel was deleted
            mock_delete.assert_called_once_with(
                reason="Empty managed voice channel cleanup"
            )

        # Verify cleanup occurred
        assert channel.id not in voice_service.managed_voice_channels

        # Verify database cleanup
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel.id,),
            )
            count = await cursor.fetchone()
            assert count[0] == 0

    @pytest.mark.asyncio
    async def test_no_cleanup_when_members_present(self, voice_service_with_bot):
        """Test no cleanup when channel still has members."""
        voice_service, mock_bot = voice_service_with_bot

        # Create channel with members
        mock_member1 = MagicMock()
        mock_member2 = MagicMock()
        channel = MockVoiceChannel(
            channel_id=12346, members=[mock_member1, mock_member2]
        )
        mock_bot.add_channel(channel)

        # Add to managed channels and database
        voice_service.managed_voice_channels.add(channel.id)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Mock member leaving (but others remain)
        leaving_member = MagicMock()
        leaving_member.display_name = "LeavingUser"

        with patch.object(channel, "delete", new_callable=AsyncMock) as mock_delete:
            await voice_service._handle_channel_left(channel, leaving_member)

            # Verify channel was NOT deleted
            mock_delete.assert_not_called()

        # Verify channel still managed
        assert channel.id in voice_service.managed_voice_channels

        # Verify database still has entry
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel.id,),
            )
            count = await cursor.fetchone()
            assert count[0] == 1

    @pytest.mark.asyncio
    async def test_startup_reconciliation_missing_channels(
        self, voice_service_with_bot
    ):
        """Test startup reconciliation removes missing channels from database."""
        voice_service, _mock_bot = voice_service_with_bot

        # Add non-existent channels to database
        missing_channel_ids = [99997, 99998, 99999]

        async with Database.get_connection() as db:
            for i, channel_id in enumerate(missing_channel_ids):
                await db.execute(
                    """
                    INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (12345, 67890, 11111 + i, channel_id, 1234567890, 1234567890, 1),
                )
            await db.commit()

        # Clear managed channels and reload
        voice_service.managed_voice_channels.clear()
        await voice_service._load_managed_channels()

        # Verify missing channels are not in managed set
        for channel_id in missing_channel_ids:
            assert channel_id not in voice_service.managed_voice_channels

        # Run reconciliation to properly handle missing channels
        await voice_service.reconcile_all_guilds_on_ready()

        # Reconciliation should remove the stale rows entirely once it confirms the
        # channels no longer exist on Discord.
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id IN (?, ?, ?)",
                missing_channel_ids,
            )
            count = await cursor.fetchone()
            assert count[0] == 0

    @pytest.mark.asyncio
    async def test_startup_reconciliation_active_channels(self, voice_service_with_bot):
        """Test startup reconciliation resumes management of channels with members."""
        voice_service, mock_bot = voice_service_with_bot

        # Create channels with members
        active_channels = []
        for i in range(3):
            channel_id = 88880 + i
            mock_member = MagicMock()
            channel = MockVoiceChannel(channel_id=channel_id, members=[mock_member])
            mock_bot.add_channel(channel)
            active_channels.append(channel)

            # Add to database
            async with Database.get_connection() as db:
                await db.execute(
                    """
                    INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (12345, 67890, 11111 + i, channel_id, 1234567890, 1234567890, 1),
                )
                await db.commit()

        # Clear managed channels and reload
        voice_service.managed_voice_channels.clear()
        await voice_service._load_managed_channels()

        # Verify active channels are in managed set
        for channel in active_channels:
            assert channel.id in voice_service.managed_voice_channels

        # Verify database entries remain
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id IN (?, ?, ?)",
                [ch.id for ch in active_channels],
            )
            count = await cursor.fetchone()
            assert count[0] == 3

    @pytest.mark.asyncio
    async def test_startup_reconciliation_empty_channels_scheduled(
        self, voice_service_with_bot
    ):
        """Test startup reconciliation adds empty channels to managed set in delayed mode."""
        voice_service, mock_bot = voice_service_with_bot

        # Create empty channels
        empty_channels = []
        for i in range(2):
            channel_id = 77770 + i
            channel = MockVoiceChannel(channel_id=channel_id, members=[])  # Empty
            mock_bot.add_channel(channel)
            empty_channels.append(channel)

            # Add to database
            async with Database.get_connection() as db:
                await db.execute(
                    """
                    INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (12345, 67890, 22222 + i, channel_id, 1234567890, 1234567890, 1),
                )
                await db.commit()

        # Mock config to return delayed mode
        with patch.object(
            voice_service.config_service, "get_global_setting"
        ) as mock_config:
            mock_config.return_value = "delayed"

            # Clear managed channels and reload
            voice_service.managed_voice_channels.clear()
            await voice_service._load_managed_channels()

            # Verify channels are added to managed set (delayed mode)
            # In delayed mode, _load_managed_channels adds empty channels to managed set
            # and defers cleanup decision to reconciliation
            for channel in empty_channels:
                assert channel.id in voice_service.managed_voice_channels

    @pytest.mark.asyncio
    async def test_startup_reconciliation_empty_channels_immediate_cleanup(
        self, voice_service_with_bot
    ):
        """Test startup reconciliation immediately cleans up empty channels in immediate mode."""
        voice_service, mock_bot = voice_service_with_bot

        # Create empty channels
        empty_channels = []
        for i in range(2):
            channel_id = 77880 + i
            channel = MockVoiceChannel(channel_id=channel_id, members=[])  # Empty
            mock_bot.add_channel(channel)
            empty_channels.append(channel)

            # Add to database
            async with Database.get_connection() as db:
                await db.execute(
                    """
                    INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (12345, 67890, 33333 + i, channel_id, 1234567890, 1234567890, 1),
                )
                await db.commit()

        # Mock config to return immediate mode (default)
        with patch.object(
            voice_service.config_service, "get_global_setting"
        ) as mock_config:
            mock_config.return_value = "immediate"

            # Mock the cleanup method to track calls
            with patch.object(
                voice_service, "_cleanup_empty_channel", new_callable=AsyncMock
            ) as mock_cleanup:
                # Mock the schedule cleanup method to ensure it's not called
                with patch.object(
                    voice_service, "_schedule_channel_cleanup", new_callable=AsyncMock
                ) as mock_schedule:
                    # Clear managed channels and reload
                    voice_service.managed_voice_channels.clear()
                    await voice_service._load_managed_channels()

                    # Verify channels are NOT added to managed set (immediate mode)
                    for channel in empty_channels:
                        assert channel.id not in voice_service.managed_voice_channels

                    # Verify immediate cleanup was called for each empty channel
                    assert mock_cleanup.call_count == len(empty_channels)
                    cleaned_channel_ids = [
                        call[0][0] for call in mock_cleanup.call_args_list
                    ]
                    for channel in empty_channels:
                        assert channel.id in cleaned_channel_ids

                    # Verify no scheduled cleanup was called
                    mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_startup_reconciliation_default_delayed_mode(
        self, voice_service_with_bot
    ):
        """Test that startup reconciliation defaults to delayed cleanup mode."""
        voice_service, mock_bot = voice_service_with_bot

        # Create empty channel
        channel_id = 77990
        channel = MockVoiceChannel(channel_id=channel_id, members=[])
        mock_bot.add_channel(channel)

        # Add to database
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 44444, channel_id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Mock the cleanup method to track calls (don't mock config - use default)
        with patch.object(
            voice_service, "_cleanup_empty_channel", new_callable=AsyncMock
        ) as mock_cleanup:
            # Clear managed channels and reload
            voice_service.managed_voice_channels.clear()
            await voice_service._load_managed_channels()

            # Verify channel IS added to managed set (default delayed mode)
            assert channel_id in voice_service.managed_voice_channels

            # Verify NO immediate cleanup was called (delayed mode)
            mock_cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_scheduled_cleanup_fallback(self, voice_service_with_bot):
        """Test scheduled cleanup works as fallback for empty channels."""
        voice_service, mock_bot = voice_service_with_bot

        # Create empty channel
        channel = MockVoiceChannel(channel_id=66666, members=[])
        mock_bot.add_channel(channel)
        voice_service.managed_voice_channels.add(channel.id)

        # Add to database
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Set very short cleanup delay for testing
        with (
            patch.object(
                voice_service.config_service, "get_global_setting", return_value=0.1
            ),
            patch.object(channel, "delete", new_callable=AsyncMock) as mock_delete,
        ):
            # Schedule cleanup and wait
            await voice_service._schedule_channel_cleanup(channel.id)
            await asyncio.sleep(0.2)  # Wait for cleanup to complete

            # Verify channel was deleted
            mock_delete.assert_called_once()

        # Verify cleanup
        assert channel.id not in voice_service.managed_voice_channels

        # Verify database cleanup
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel.id,),
            )
            count = await cursor.fetchone()
            assert count[0] == 0

    @pytest.mark.asyncio
    async def test_scheduled_cleanup_skips_active_channel(self, voice_service_with_bot):
        """Test scheduled cleanup skips channels that become active."""
        voice_service, mock_bot = voice_service_with_bot

        # Create initially empty channel
        channel = MockVoiceChannel(channel_id=55555, members=[])
        mock_bot.add_channel(channel)
        voice_service.managed_voice_channels.add(channel.id)

        # Set very short cleanup delay for testing
        with (
            patch.object(
                voice_service.config_service, "get_global_setting", return_value=0.1
            ),
            patch.object(channel, "delete", new_callable=AsyncMock) as mock_delete,
        ):
            # Schedule cleanup
            await voice_service._schedule_channel_cleanup(channel.id)

            # Add a member before cleanup occurs
            mock_member = MagicMock()
            channel.members.append(mock_member)

            await asyncio.sleep(0.2)  # Wait for cleanup attempt

            # Verify channel was NOT deleted
            mock_delete.assert_not_called()

        # Channel should still be managed
        assert channel.id in voice_service.managed_voice_channels

    @pytest.mark.asyncio
    async def test_cleanup_channel_not_found_exception(self, voice_service_with_bot):
        """Test cleanup handles discord.NotFound exception gracefully."""
        voice_service, mock_bot = voice_service_with_bot

        # Create and set up a channel
        channel = MockVoiceChannel(channel_id=12347, members=[])
        mock_bot.add_channel(channel)

        # Add to managed channels and database
        voice_service.managed_voice_channels.add(channel.id)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Mock discord.NotFound exception on delete
        import discord

        with patch.object(channel, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = discord.NotFound(MagicMock(), "Channel not found")

            # Should not raise exception
            await voice_service._cleanup_empty_channel(channel)

            # Verify delete was attempted
            mock_delete.assert_called_once()

        # Verify cleanup occurred anyway (cache and DB)
        assert channel.id not in voice_service.managed_voice_channels

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel.id,),
            )
            count = await cursor.fetchone()
            assert count[0] == 0

    @pytest.mark.asyncio
    async def test_cleanup_channel_forbidden_exception(self, voice_service_with_bot):
        """Test cleanup handles discord.Forbidden exception gracefully."""
        voice_service, mock_bot = voice_service_with_bot

        # Create and set up a channel
        channel = MockVoiceChannel(channel_id=12348, members=[])
        mock_bot.add_channel(channel)

        # Add to managed channels and database
        voice_service.managed_voice_channels.add(channel.id)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Mock discord.Forbidden exception on delete
        import discord

        with patch.object(channel, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = discord.Forbidden(
                MagicMock(), "Insufficient permissions"
            )

            # Should not raise exception
            await voice_service._cleanup_empty_channel(channel)

            # Verify delete was attempted
            mock_delete.assert_called_once()

        # Verify cleanup occurred anyway (cache and DB)
        assert channel.id not in voice_service.managed_voice_channels

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel.id,),
            )
            count = await cursor.fetchone()
            assert count[0] == 0

    @pytest.mark.asyncio
    async def test_cleanup_with_channel_id_none_channel(self, voice_service_with_bot):
        """Test cleanup with channel ID when bot.get_channel returns None."""
        voice_service, _mock_bot = voice_service_with_bot

        # Add channel to managed channels and database without adding to bot
        channel_id = 12349
        voice_service.managed_voice_channels.add(channel_id)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, channel_id, 1234567890, 1234567890, 1),
            )
            await db.commit()

        # Call cleanup with channel ID (bot.get_channel will return None)
        await voice_service._cleanup_empty_channel(channel_id)

        # Verify cleanup occurred (cache and DB)
        assert channel_id not in voice_service.managed_voice_channels

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel_id,),
            )
            count = await cursor.fetchone()
            assert count[0] == 0
