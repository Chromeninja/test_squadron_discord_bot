"""
Test for multiple channels per owner per JTC functionality.

Verifies that joining a JTC channel always creates a new channel,
even when the user already has an active channel from the same JTC.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


class MockVoiceChannel:
    """Mock Discord voice channel."""

    def __init__(
        self, channel_id: int, name: str = "test-channel", members: list | None = None, category=None
    ):
        self.id = channel_id
        self.name = name
        self.members = members or []
        self.category = category or MagicMock()
        self.guild = MagicMock()
        self.guild.id = 12345
        self.user_limit = 0
        self.bitrate = 64000

    async def delete(self, reason: str | None = None):
        """Mock channel deletion."""
        pass


class MockMember:
    """Mock Discord member."""

    def __init__(self, user_id: int, display_name: str = "TestUser"):
        self.id = user_id
        self.display_name = display_name
        self.voice = MagicMock()
        self.voice.channel = None
        self.top_role = MagicMock()
        self.top_role.name = "member"

    async def move_to(self, channel):
        """Mock member move."""
        pass

    async def send(self, message: str):
        """Mock sending DM to member."""
        pass


class MockGuild:
    """Mock Discord guild."""

    def __init__(self, guild_id: int = 12345):
        self.id = guild_id
        self.name = "Test Guild"

    def get_channel(self, channel_id: int):
        """Mock get_channel method."""
        return None

    def get_member(self, user_id: int):
        """Mock get_member method."""
        return None

    async def create_voice_channel(self, name: str, category=None, **kwargs):
        """Mock voice channel creation."""
        return MockVoiceChannel(channel_id=99999, name=name, category=category)


class MockBot:
    """Mock Discord bot."""

    def __init__(self):
        self._channels = {}
        self.guilds = []
        self.user = MagicMock()
        self.user.id = 12345

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


class TestMultipleChannelsPerOwner:
    """Tests for multiple channels per owner per JTC functionality."""

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
    async def test_jtc_join_creates_new_channel_when_user_has_existing_active_channel(self, voice_service_with_bot):
        """Test that joining JTC when user already has a channel creates a new channel."""
        voice_service, mock_bot = voice_service_with_bot

        # Setup guild and JTC channel
        guild = MockGuild(guild_id=12345)
        jtc_channel = MockVoiceChannel(
            channel_id=67890,
            name="Join to Create",
            category=MagicMock()
        )
        member = MockMember(user_id=11111, display_name="TestUser")

        # Create an existing active channel for the user
        existing_channel = MockVoiceChannel(
            channel_id=55555,
            name="TestUser's Existing Channel",
            members=[member]
        )
        mock_bot.add_channel(existing_channel)

        # Add existing channel to database
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 55555, int(time.time()), int(time.time()), 1),
            )
            await db.commit()

        # Mock channel permissions check
        bot_member = MagicMock()
        bot_member.top_role = MagicMock()
        bot_member.top_role.name = "bot"
        member.top_role.name = "member"

        # Mock guild methods
        guild.get_member = MagicMock(return_value=bot_member)

        # Mock category permissions
        jtc_channel.category.permissions_for = MagicMock()
        jtc_channel.category.permissions_for.return_value.manage_channels = True

        # Mock channel creation
        new_channel = MockVoiceChannel(channel_id=77777, name="TestUser's Channel")

        with patch.object(guild, 'create_voice_channel', return_value=new_channel) as mock_create:
            with patch('helpers.voice_permissions.enforce_permission_changes') as mock_enforce:
                with patch('helpers.discord_api.channel_send_message') as mock_send:
                    # Mock cooldown check to allow creation
                    with patch.object(voice_service, 'can_create_voice_channel', return_value=(True, None)):
                        # Call the JTC handler
                        await voice_service._handle_join_to_create(guild, jtc_channel, member)

                        # Verify a new channel was created (not redirected to existing)
                        mock_create.assert_called_once()

                        # Verify the member was not moved to existing channel
                        # (if redirect happened, move_to wouldn't be called on member)

                        # Check database has both channels
                        async with Database.get_connection() as db:
                            cursor = await db.execute(
                                """SELECT COUNT(*) FROM voice_channels 
                                   WHERE guild_id = ? AND owner_id = ? AND is_active = 1""",
                                (12345, 11111)
                            )
                            count = await cursor.fetchone()
                            # Should have 2 active channels for the same user
                            assert count[0] == 2

    @pytest.mark.asyncio
    async def test_cleanup_by_channel_id_only_affects_specific_channel(self, voice_service_with_bot):
        """Test that cleanup_by_channel_id only affects the specific channel."""
        voice_service, mock_bot = voice_service_with_bot

        # Create multiple channels for the same user
        async with Database.get_connection() as db:
            # Channel 1
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 55555, int(time.time()), int(time.time()), 1),
            )
            # Channel 2
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 66666, int(time.time()), int(time.time()), 1),
            )

            # Add settings for both channels
            await db.execute(
                """
                INSERT INTO voice_channel_settings
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key, setting_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 55555, "channel_name", "Channel 1"),
            )
            await db.execute(
                """
                INSERT INTO voice_channel_settings
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key, setting_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 66666, "channel_name", "Channel 2"),
            )
            await db.commit()

        # Cleanup only one channel
        await voice_service.cleanup_by_channel_id(55555)

        # Verify only one channel was deactivated
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """SELECT is_active FROM voice_channels WHERE voice_channel_id = ?""",
                (55555,)
            )
            channel1_active = await cursor.fetchone()
            assert channel1_active[0] == 0  # Should be deactivated

            cursor = await db.execute(
                """SELECT is_active FROM voice_channels WHERE voice_channel_id = ?""",
                (66666,)
            )
            channel2_active = await cursor.fetchone()
            assert channel2_active[0] == 1  # Should still be active

            # Verify settings were cleaned up only for the specific channel
            cursor = await db.execute(
                """SELECT COUNT(*) FROM voice_channel_settings WHERE voice_channel_id = ?""",
                (55555,)
            )
            settings1_count = await cursor.fetchone()
            assert settings1_count[0] == 0  # Settings should be deleted

            cursor = await db.execute(
                """SELECT COUNT(*) FROM voice_channel_settings WHERE voice_channel_id = ?""",
                (66666,)
            )
            settings2_count = await cursor.fetchone()
            assert settings2_count[0] == 1  # Settings should remain

    @pytest.mark.asyncio
    async def test_get_user_voice_channel_returns_latest_for_jtc(self, voice_service_with_bot):
        """Test that get_user_voice_channel returns the most recent channel for a JTC."""
        voice_service, mock_bot = voice_service_with_bot

        # Create multiple channels for the same user and JTC
        base_time = int(time.time())
        async with Database.get_connection() as db:
            # Older channel
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 55555, base_time - 100, base_time - 100, 1),
            )
            # Newer channel
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (12345, 67890, 11111, 66666, base_time, base_time, 1),
            )
            await db.commit()

        # Get user's channel - should return the newest one
        channel_id = await voice_service.get_user_voice_channel(12345, 67890, 11111)
        assert channel_id == 66666  # Should return the newer channel
