"""
Test for multiple channels per owner per JTC functionality.

Verifies that joining a JTC channel always creates a new channel,
even when the user already has an active channel from the same JTC.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService


class MockVoiceChannel:
    """Mock Discord voice channel."""

    def __init__(
        self,
        channel_id: int,
        name: str = "test-channel",
        members: list | None = None,
        category=None,
        guild=None,
    ):
        self.id = channel_id
        self.name = name
        self.members = members or []
        self.category = category or MagicMock()
        self.guild = guild or MagicMock()
        self.guild.id = 12345
        if not hasattr(self.guild, "get_member"):
            self.guild.get_member = MagicMock(return_value=None)
        self.user_limit = 0
        self.bitrate = 64000
        self.overwrites = {}
        self.mention = f"<#{channel_id}>"

    async def delete(self, reason: str | None = None):
        """Mock channel deletion."""
        pass

    async def edit(self, **kwargs):
        """Mock channel edit operation."""
        overwrites = kwargs.get("overwrites")
        if overwrites is not None:
            self.overwrites = overwrites


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

    def get_guild(self, guild_id: int):
        """Get mock guild by ID."""
        return None

    def get_channel(self, channel_id: int):
        """Get mock channel by ID."""
        return self._channels.get(channel_id)

    async def fetch_channel(self, channel_id: int):
        """Fetch mock channel by ID (async version)."""
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
    async def test_jtc_join_creates_new_channel_when_user_has_existing_active_channel(
        self, voice_service_with_bot
    ):
        """Test that joining JTC when user already has a channel cleans up old channel and creates new one."""
        voice_service, mock_bot = voice_service_with_bot

        # Setup guild and JTC channel
        guild = MockGuild(guild_id=12345)
        jtc_channel = MockVoiceChannel(
            channel_id=67890, name="Join to Create", category=MagicMock()
        )
        member = MockMember(user_id=11111, display_name="TestUser")
        # Set member as connected to the JTC channel
        member.voice.channel = jtc_channel
        member.mention = f"<@{member.id}>"  # Add mention attribute

        # Create an existing active channel for the user
        existing_channel = MockVoiceChannel(
            channel_id=55555,
            name="TestUser's Existing Channel",
            members=[],  # Empty so it can be cleaned up
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
        # Create mock roles that can be compared (role position is higher = higher privilege)
        bot_role = MagicMock()
        bot_role.position = 10
        bot_role.name = "bot"

        member_role = MagicMock()
        member_role.position = 5
        member_role.name = "member"

        bot_member = MagicMock()
        bot_member.top_role = bot_role
        member.top_role = member_role

        # Mock guild methods
        guild.get_member = MagicMock(return_value=bot_member)

        # Mock category permissions
        jtc_channel.category.permissions_for = MagicMock()
        jtc_channel.category.permissions_for.return_value.manage_channels = True

        # Mock channel creation
        new_channel = MockVoiceChannel(channel_id=77777, name="TestUser's Channel")
        # Add the new channel to the mock bot so it can be found during reconciliation
        mock_bot.add_channel(new_channel)

        with patch.object(
            guild, "create_voice_channel", return_value=new_channel
        ) as mock_create:
            with patch("helpers.voice_permissions.enforce_permission_changes"):
                with patch("helpers.discord_api.channel_send_message"):
                    # Mock cooldown check to allow creation
                    with patch.object(
                        voice_service,
                        "can_create_voice_channel",
                        return_value=(True, None),
                    ):
                        # Call the JTC handler
                        await voice_service._handle_join_to_create(
                            guild, jtc_channel, member
                        )

                        # Verify a new channel was created
                        mock_create.assert_called_once()

                        # Wait for background cleanup task to complete
                        await asyncio.sleep(0.1)

                        # Check database: old channel should be cleaned up (is_active=0)
                        # and only the new channel should be active
                        async with Database.get_connection() as db:
                            cursor = await db.execute(
                                """SELECT COUNT(*) FROM voice_channels
                                   WHERE guild_id = ? AND owner_id = ? AND is_active = 1""",
                                (12345, 11111),
                            )
                            count = await cursor.fetchone()
                            # Should have only 1 active channel (old one cleaned up)
                            assert count[0] == 1

                            # Verify the old channel was marked inactive
                            cursor = await db.execute(
                                """SELECT is_active FROM voice_channels
                                   WHERE voice_channel_id = ?""",
                                (55555,),
                            )
                            old_channel_status = await cursor.fetchone()
                            assert old_channel_status is None, (
                                "Old channel should be removed once replaced"
                            )

    @pytest.mark.asyncio
    async def test_cleanup_by_channel_id_only_affects_specific_channel(
        self, voice_service_with_bot
    ):
        """Test that cleanup_by_channel_id only affects the specific channel."""
        voice_service, _mock_bot = voice_service_with_bot

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

        # Verify the specific channel was fully removed
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """SELECT is_active FROM voice_channels WHERE voice_channel_id = ?""",
                (55555,),
            )
            channel1_active = await cursor.fetchone()
            assert channel1_active is None  # Row should be deleted entirely

            cursor = await db.execute(
                """SELECT is_active FROM voice_channels WHERE voice_channel_id = ?""",
                (66666,),
            )
            channel2_active = await cursor.fetchone()
            assert channel2_active is not None and channel2_active[0] == 1

            # Verify settings were cleaned up only for the specific channel
            cursor = await db.execute(
                """SELECT COUNT(*) FROM voice_channel_settings WHERE voice_channel_id = ?""",
                (55555,),
            )
            settings1_count = await cursor.fetchone()
            assert settings1_count[0] == 0  # Settings should be deleted

            cursor = await db.execute(
                """SELECT COUNT(*) FROM voice_channel_settings WHERE voice_channel_id = ?""",
                (66666,),
            )
            settings2_count = await cursor.fetchone()
            assert settings2_count[0] == 1  # Settings should remain

    @pytest.mark.asyncio
    async def test_get_user_voice_channel_returns_latest_for_jtc(
        self, voice_service_with_bot
    ):
        """Test that get_user_voice_channel returns the most recent channel for a JTC."""
        voice_service, _mock_bot = voice_service_with_bot

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

    @pytest.mark.asyncio
    async def test_store_user_channel_marks_channel_orphan_when_occupied(
        self, voice_service_with_bot
    ):
        """Ensure populated legacy channels are preserved and marked ownerless."""
        voice_service, mock_bot = voice_service_with_bot

        guild_id = 12345
        jtc_channel_id = 67890
        owner_id = 11111
        old_channel_id = 55555
        new_channel_id = 77777

        previous_owner_member = MagicMock()
        existing_channel = MockVoiceChannel(
            channel_id=old_channel_id,
            name="Existing",
            members=[MagicMock()],
        )
        existing_channel.guild.get_member = MagicMock(
            return_value=previous_owner_member
        )
        existing_channel.overwrites = {previous_owner_member: MagicMock()}
        mock_bot.add_channel(existing_channel)

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
                    owner_id,
                    old_channel_id,
                    int(time.time()),
                    int(time.time()),
                    1,
                ),
            )
            await db.execute(
                """
                INSERT INTO voice_channel_settings
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key, setting_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    guild_id,
                    jtc_channel_id,
                    owner_id,
                    old_channel_id,
                    "channel_name",
                    "Legacy",
                ),
            )
            await db.commit()

        await voice_service._store_user_channel(
            guild_id, jtc_channel_id, owner_id, new_channel_id
        )

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
                (old_channel_id,),
            )
            orphan_row = await cursor.fetchone()
            assert orphan_row is not None
            assert orphan_row[0] == VoiceService.ORPHAN_OWNER_ID

            cursor = await db.execute(
                "SELECT previous_owner_id FROM voice_channels WHERE voice_channel_id = ?",
                (old_channel_id,),
            )
            previous_owner_row = await cursor.fetchone()
            assert previous_owner_row is not None
            assert previous_owner_row[0] == owner_id

            cursor = await db.execute(
                "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
                (new_channel_id,),
            )
            new_row = await cursor.fetchone()
            assert new_row is not None and new_row[0] == owner_id

            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channel_settings WHERE voice_channel_id = ?",
                (old_channel_id,),
            )
            settings_count = await cursor.fetchone()
            assert settings_count is not None
            assert settings_count[0] == 1

        # Ensure overwrites for the previous owner were removed
        assert previous_owner_member not in existing_channel.overwrites

    @pytest.mark.asyncio
    async def test_claim_voice_channel_allows_orphaned_channel(
        self, voice_service_with_bot
    ):
        """Verify /voice claim succeeds when a channel has been orphaned."""
        voice_service, _mock_bot = voice_service_with_bot

        guild = MockGuild(guild_id=12345)
        channel = MockVoiceChannel(
            channel_id=88888, name="Orphan", members=[], guild=guild
        )
        user = MockMember(user_id=22222, display_name="Claimer")
        user.voice.channel = channel
        channel.members = [user]
        jtc_channel_id = 67890

        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    guild.id,
                    jtc_channel_id,
                    VoiceService.ORPHAN_OWNER_ID,
                    channel.id,
                    int(time.time()),
                    int(time.time()),
                    1,
                ),
            )
            await db.commit()

        with (
            patch(
                "helpers.voice_repo.transfer_channel_owner",
                new=AsyncMock(return_value=True),
            ) as transfer_mock,
            patch(
                "helpers.permissions_helper.update_channel_owner", new=AsyncMock()
            ) as perms_mock,
        ):
            result = await voice_service.claim_voice_channel(guild.id, user.id, user)

        assert result.success
        transfer_mock.assert_awaited_once_with(
            voice_channel_id=channel.id,
            new_owner_id=user.id,
            guild_id=guild.id,
            jtc_channel_id=jtc_channel_id,
        )
        perms_mock.assert_awaited_once_with(
            channel=channel,
            new_owner_id=user.id,
            previous_owner_id=VoiceService.ORPHAN_OWNER_ID,
            guild_id=guild.id,
            jtc_channel_id=jtc_channel_id,
        )
