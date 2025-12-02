"""
Tests for voice settings functionality.

This file contains tests for the new voice settings helper functions
and the updated channel creation with settings loading.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.voice_settings import _get_all_user_settings, fetch_channel_settings
from services.config_service import ConfigService
from services.voice_service import VoiceService


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock(spec=discord.Client)
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.default_role = MagicMock(spec=discord.Role)
    return guild


@pytest.fixture
def mock_member():
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 67890
    member.display_name = "TestUser"
    member.display_avatar = MagicMock()
    member.display_avatar.url = "http://example.com/avatar.png"
    return member


@pytest.fixture
def mock_voice_channel():
    """Create a mock Discord voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 98765
    channel.name = "TestUser's Channel"
    channel.bitrate = 64000
    channel.user_limit = 10
    channel.category = MagicMock()
    channel.members = []
    return channel


@pytest.fixture
def mock_jtc_channel():
    """Create a mock join-to-create voice channel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 55555
    channel.name = "Join to Create"
    channel.bitrate = 64000
    channel.user_limit = 0
    channel.category = MagicMock()
    return channel


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 12345
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 67890
    interaction.user.voice = None  # Default to not in voice
    return interaction


@pytest.fixture
def voice_service(mock_bot):
    """Create a VoiceService instance for testing."""
    config_service = MagicMock(spec=ConfigService)
    service = VoiceService(config_service, mock_bot)
    # Skip actual initialization
    service._initialized = True
    return service


class TestVoiceSettingsHelper:
    """Tests for the voice settings helper functions."""

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_no_voice_no_saved(
        self, mock_bot, mock_interaction
    ):
        """Test fetch_channel_settings when user has no active voice and no saved settings."""
        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            # Mock no active channel
            cursor = AsyncMock()
            cursor.fetchone.return_value = None
            cursor.fetchall.return_value = []
            mock_conn.execute.return_value = cursor

            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["settings"] is None
            assert result["active_channel"] is None
            assert result["is_active"] is False
            assert result["jtc_channel_id"] is None
            assert result["embeds"] == []

    @pytest.mark.asyncio
    async def test_fetch_channel_settings_active_voice_with_settings(
        self, mock_bot, mock_interaction, mock_voice_channel
    ):
        """Test fetch_channel_settings when user is in an active voice channel with settings."""
        # Setup user in voice channel
        mock_interaction.user.voice = MagicMock()
        mock_interaction.user.voice.channel = mock_voice_channel

        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            # Mock finding the JTC channel for active voice
            cursor.fetchone.side_effect = [
                (55555,),  # jtc_channel_id from user_voice_channels
                ("Test Channel", 5, 1),  # channel_settings
            ]
            cursor.fetchall.side_effect = [
                [(1001, "user", "permit")],  # permissions
                [(1001, "user", 1)],  # ptt_settings
                [],  # priority_settings
                [],  # soundboard_settings
            ]
            mock_conn.execute.return_value = cursor

            result = await fetch_channel_settings(
                mock_bot, mock_interaction, allow_inactive=True
            )

            assert result["is_active"] is True
            assert result["active_channel"] == mock_voice_channel
            assert result["jtc_channel_id"] == 55555
            assert result["settings"] is not None
            assert result["settings"]["channel_name"] == "Test Channel"
            assert len(result["embeds"]) == 1

    @pytest.mark.asyncio
    async def test_get_all_user_settings_comprehensive(self):
        """Test _get_all_user_settings returns comprehensive settings."""
        with patch("helpers.voice_settings.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = ("Custom Channel", 8, 1)  # channel_settings
            cursor.fetchall.side_effect = [
                [(1001, "user", "permit"), (1002, "role", "reject")],  # permissions
                [(1001, "user", 1)],  # ptt_settings
                [(1001, "user", 1)],  # priority_settings
                [(1002, "role", 0)],  # soundboard_settings
            ]
            mock_conn.execute.return_value = cursor

            settings = await _get_all_user_settings(12345, 55555, 67890)

            assert settings["channel_name"] == "Custom Channel"
            assert settings["user_limit"] == 8
            assert settings["lock"] is True
            assert len(settings["permissions"]) == 2
            assert len(settings["ptt_settings"]) == 1
            assert len(settings["priority_settings"]) == 1
            assert len(settings["soundboard_settings"]) == 1


class TestVoiceServiceChannelCreation:
    """Tests for voice service channel creation with settings loading."""

    @pytest.mark.parametrize(
        "channel_name,user_limit,lock,expected_name,expected_limit",
        [
            # Test with saved settings
            ("My Custom Channel", 5, 1, "My Custom Channel", 5),
            ("🎮 Gaming Room", 10, 0, "🎮 Gaming Room", 10),
            (
                "Valid Channel",
                0,
                1,
                "Valid Channel",
                0,
            ),  # Edge case: zero limit but valid name
            ("Unicode Channel 你好", 99, 0, "Unicode Channel 你好", 99),
            # Test with no saved settings (None values)
            (None, None, None, "TestUser's Channel", 0),  # Should use defaults
        ],
    )
    @pytest.mark.asyncio
    async def test_create_user_channel_parametrized(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
        channel_name,
        user_limit,
        lock,
        expected_name,
        expected_limit,
    ):
        """Test _create_user_channel with various saved settings and defaults."""
        import discord

        # Configure database response
        if channel_name is None:
            # No saved settings case
            mock_db_connection.set_fetchone_result(None)
        else:
            # Saved settings case
            mock_db_connection.set_fetchone_result((channel_name, user_limit, lock))

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = expected_name
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock bot member for role comparison
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=True)
        mock_guild.get_member.return_value = mock_bot_member

        # Mock enforce_permission_changes and channel_send_message
        with (
            patch("services.voice_service.enforce_permission_changes") as mock_enforce,
            patch("services.voice_service.channel_send_message") as mock_send,
        ):
            mock_enforce.return_value = None
            mock_send.return_value = None

            await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

            # Verify channel was created with expected settings
            mock_guild.create_voice_channel.assert_called_once()
            create_args = mock_guild.create_voice_channel.call_args

            assert create_args.kwargs["name"] == expected_name

            # For no saved settings, should use JTC channel's user_limit
            if channel_name is None:
                assert create_args.kwargs["user_limit"] == mock_jtc_channel.user_limit
            else:
                assert create_args.kwargs["user_limit"] == expected_limit

    @pytest.mark.asyncio
    async def test_create_user_channel_empty_name_fallback(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that empty channel names fall back to default."""
        import discord

        # Test case: saved settings with empty name should fall back to default
        mock_db_connection.set_fetchone_result(("", 5, 1))

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "TestUser's Channel"
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock bot member for role comparison
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.__gt__ = MagicMock(return_value=True)
        mock_guild.get_member.return_value = mock_bot_member

        # Mock enforce_permission_changes and channel_send_message
        with (
            patch("services.voice_service.enforce_permission_changes") as mock_enforce,
            patch("services.voice_service.channel_send_message") as mock_send,
        ):
            mock_enforce.return_value = None
            mock_send.return_value = None

            await voice_service._create_user_channel(
                mock_guild, mock_jtc_channel, mock_member
            )

            # Verify channel was created with fallback name
            mock_guild.create_voice_channel.assert_called_once()
            create_args = mock_guild.create_voice_channel.call_args

            assert (
                create_args.kwargs["name"] == "TestUser's Channel"
            )  # Should fallback to default
            assert create_args.kwargs["user_limit"] == 5  # Should use saved limit

    @pytest.mark.asyncio
    async def test_create_user_channel_applies_saved_settings(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that _create_user_channel applies saved settings during creation."""
        import discord

        # Configure saved settings
        mock_db_connection.set_fetchone_result(("My Custom Channel", 5, 1))

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        created_channel.name = "My Custom Channel"
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock enforce_permission_changes
        with patch("services.voice_service.enforce_permission_changes") as mock_enforce:
            mock_enforce.return_value = None

            # Mock channel_send_message
            with patch("services.voice_service.channel_send_message") as mock_send:
                mock_send.return_value = None

                await voice_service._create_user_channel(
                    mock_guild, mock_jtc_channel, mock_member
                )

                # Verify channel was created with saved settings
                mock_guild.create_voice_channel.assert_called_once()
                create_args = mock_guild.create_voice_channel.call_args

                assert create_args.kwargs["name"] == "My Custom Channel"
                assert create_args.kwargs["user_limit"] == 5

                # Verify settings were applied
                mock_enforce.assert_called_once()

                # Verify ChannelSettingsView was posted
                mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_channel_uses_defaults_no_saved_settings(
        self,
        voice_service,
        mock_guild,
        mock_jtc_channel,
        mock_member,
        mock_db_connection,
    ):
        """Test that _create_user_channel uses defaults when no saved settings exist."""
        import discord

        # Mock no saved settings
        mock_db_connection.set_fetchone_result(None)

        # Mock guild.create_voice_channel
        created_channel = AsyncMock(spec=discord.VoiceChannel)
        created_channel.id = 99999
        mock_guild.create_voice_channel.return_value = created_channel

        # Mock member move
        mock_member.move_to = AsyncMock()

        # Mock enforce_permission_changes
        with patch("services.voice_service.enforce_permission_changes"):
            # Mock channel_send_message
            with patch("services.voice_service.channel_send_message"):
                await voice_service._create_user_channel(
                    mock_guild, mock_jtc_channel, mock_member
                )

                # Verify channel was created with default settings
                mock_guild.create_voice_channel.assert_called_once()
                create_args = mock_guild.create_voice_channel.call_args

                # Should use default name format
                assert (
                    create_args.kwargs["name"]
                    == f"{mock_member.display_name}'s Channel"
                )
                # Should use JTC channel's user_limit
                assert create_args.kwargs["user_limit"] == mock_jtc_channel.user_limit

    @pytest.mark.parametrize(
        "channel_name,user_limit,lock,expected_name,expected_limit,expected_lock",
        [
            # Test various valid settings
            ("Custom Name", 10, 0, "Custom Name", 10, False),
            ("🎮 Gaming Channel", 5, 1, "🎮 Gaming Channel", 5, True),
            (
                "Test Channel with Unicode 你好",
                99,
                0,
                "Test Channel with Unicode 你好",
                99,
                False,
            ),
            # Test edge cases
            ("", 0, 1, "", 0, True),  # Empty name, zero limit
            (
                "Very Long Channel Name That Exceeds Normal Limits",
                1,
                0,
                "Very Long Channel Name That Exceeds Normal Limits",
                1,
                False,
            ),
            # Test defaults/None handling
            (None, None, None, None, None, None),  # All None values
        ],
    )
    @pytest.mark.asyncio
    async def test_load_channel_settings_parametrized(
        self,
        voice_service,
        mock_db_connection,
        channel_name,
        user_limit,
        lock,
        expected_name,
        expected_limit,
        expected_lock,
    ):
        """Test _load_channel_settings with various parameter combinations."""
        if channel_name is None:
            # Test case where no settings exist
            mock_db_connection.set_fetchone_result(None)
            settings = await voice_service._load_channel_settings(12345, 55555, 67890)
            assert settings is None
        else:
            # Test case where settings exist
            mock_db_connection.set_fetchone_result((channel_name, user_limit, lock))
            settings = await voice_service._load_channel_settings(12345, 55555, 67890)

            assert settings["channel_name"] == expected_name
            assert settings["user_limit"] == expected_limit
            assert settings["lock"] == expected_lock

    @pytest.mark.asyncio
    async def test_load_channel_settings_success(
        self, voice_service, mock_db_connection
    ):
        """Test _load_channel_settings returns settings when they exist."""
        mock_db_connection.set_fetchone_result(("Custom Name", 10, 0))

        settings = await voice_service._load_channel_settings(12345, 55555, 67890)

        assert settings["channel_name"] == "Custom Name"
        assert settings["user_limit"] == 10
        assert settings["lock"] == 0

    @pytest.mark.asyncio
    async def test_load_channel_settings_no_settings(
        self, voice_service, mock_db_connection
    ):
        """Test _load_channel_settings returns None when no settings exist."""
        mock_db_connection.set_fetchone_result(None)

        settings = await voice_service._load_channel_settings(12345, 55555, 67890)

        assert settings is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_voice_command_integration(voice_service, mock_db_connection):
    """Integration test to verify voice command flow with fake Discord objects."""
    from unittest.mock import AsyncMock, MagicMock

    import discord

    # Create fake Discord objects
    fake_guild = MagicMock(spec=discord.Guild)
    fake_guild.id = 12345
    fake_guild.name = "Test Squadron"

    fake_member = MagicMock(spec=discord.Member)
    fake_member.id = 67890
    fake_member.display_name = "TestPilot"
    fake_member.guild = fake_guild

    # Create fake category for the JTC channel
    fake_category = MagicMock(spec=discord.CategoryChannel)
    fake_category.id = 44444
    fake_category.name = "Voice Channels"

    fake_jtc_channel = MagicMock(spec=discord.VoiceChannel)
    fake_jtc_channel.id = 55555
    fake_jtc_channel.name = "Join to Create"
    fake_jtc_channel.user_limit = 0
    fake_jtc_channel.category = fake_category
    fake_jtc_channel.bitrate = 64000

    fake_created_channel = AsyncMock(spec=discord.VoiceChannel)
    fake_created_channel.id = 99999
    fake_created_channel.name = "TestPilot's Channel"

    # Mock the guild's channel creation
    fake_guild.create_voice_channel.return_value = fake_created_channel

    # Mock member move functionality
    fake_member.move_to = AsyncMock()

    # Mock bot member for role comparison
    fake_bot_member = MagicMock()
    fake_bot_member.top_role = MagicMock()
    fake_bot_member.top_role.__gt__ = MagicMock(return_value=True)
    fake_guild.get_member.return_value = fake_bot_member

    # Set up database mock - no saved settings for this test
    mock_db_connection.set_fetchone_result(None)

    # Mock permission enforcement and messaging
    with (
        patch("services.voice_service.enforce_permission_changes") as mock_enforce,
        patch("services.voice_service.channel_send_message") as mock_send,
    ):
        mock_enforce.return_value = None
        mock_send.return_value = None

        # Execute the voice service flow: join-to-create → create channel → move member
        await voice_service._create_user_channel(
            fake_guild, fake_jtc_channel, fake_member
        )

        # Verify the integration flow worked
        # 1. Channel was created with default name (no saved settings)
        fake_guild.create_voice_channel.assert_called_once()
        create_call = fake_guild.create_voice_channel.call_args
        assert create_call.kwargs["name"] == "TestPilot's Channel"
        assert create_call.kwargs["user_limit"] == fake_jtc_channel.user_limit
        assert create_call.kwargs["category"] == fake_category

        # 2. Member was moved to the new channel
        fake_member.move_to.assert_called_once_with(fake_created_channel)

        # 3. Permissions were enforced
        mock_enforce.assert_called_once()

        # 4. Settings view was sent to channel
        mock_send.assert_called_once()
