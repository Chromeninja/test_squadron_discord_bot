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

    @pytest.mark.asyncio
    async def test_create_user_channel_applies_saved_settings(
        self, voice_service, mock_guild, mock_jtc_channel, mock_member
    ):
        """Test that _create_user_channel applies saved settings during creation."""

        # Mock the saved settings

        # Mock database interaction
        with patch("services.voice_service.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = ("My Custom Channel", 5, 1)
            mock_conn.execute.return_value = cursor

            # Mock guild.create_voice_channel
            created_channel = AsyncMock(spec=discord.VoiceChannel)
            created_channel.id = 99999
            created_channel.name = "My Custom Channel"
            mock_guild.create_voice_channel.return_value = created_channel

            # Mock member move
            mock_member.move_to = AsyncMock()

            # Mock enforce_permission_changes
            with patch(
                "services.voice_service.enforce_permission_changes"
            ) as mock_enforce:
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
        self, voice_service, mock_guild, mock_jtc_channel, mock_member
    ):
        """Test that _create_user_channel uses defaults when no saved settings exist."""

        # Mock no saved settings
        with patch("services.voice_service.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = None  # No saved settings
            mock_conn.execute.return_value = cursor

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
                    assert (
                        create_args.kwargs["user_limit"] == mock_jtc_channel.user_limit
                    )

    @pytest.mark.asyncio
    async def test_load_channel_settings_success(self, voice_service):
        """Test _load_channel_settings returns settings when they exist."""
        with patch("services.voice_service.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = ("Custom Name", 10, 0)
            mock_conn.execute.return_value = cursor

            settings = await voice_service._load_channel_settings(12345, 55555, 67890)

            assert settings["channel_name"] == "Custom Name"
            assert settings["user_limit"] == 10
            assert settings["lock"] == 0

    @pytest.mark.asyncio
    async def test_load_channel_settings_no_settings(self, voice_service):
        """Test _load_channel_settings returns None when no settings exist."""
        with patch("services.voice_service.Database") as mock_db:
            mock_conn = AsyncMock()
            mock_db.get_connection.return_value.__aenter__.return_value = mock_conn

            cursor = AsyncMock()
            cursor.fetchone.return_value = None
            mock_conn.execute.return_value = cursor

            settings = await voice_service._load_channel_settings(12345, 55555, 67890)

            assert settings is None


@pytest.mark.asyncio
async def test_voice_command_integration():
    """Integration test to verify voice commands work with the new helper."""
    # This would be a more complex integration test
    # Testing the actual command interaction would require more setup
    # but this demonstrates the test pattern
    pass
