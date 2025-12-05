"""
Tests for admin_list command functionality.

This file contains tests for the admin_list command using the new
voice settings helper.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.voice.commands import VoiceCommands


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    return bot


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 12345
    interaction.guild = MagicMock(id=12345)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.roles = [MagicMock(id=999)]  # User has admin role

    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)

    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.fixture
def mock_target_user():
    """Create a mock target user for admin commands."""
    user = MagicMock(spec=discord.Member)
    user.id = 67890
    user.display_name = "TargetUser"
    user.mention = "<@67890>"
    user.display_avatar = MagicMock()
    user.display_avatar.url = "http://example.com/avatar.png"
    return user


@pytest.fixture
def voice_commands(mock_bot):
    """Create a VoiceCommands instance for testing."""
    commands = VoiceCommands(mock_bot)
    # Mock the bot's services container
    mock_services = MagicMock()
    mock_services.voice = MagicMock()
    mock_bot.services = mock_services
    mock_bot.has_admin_permissions = AsyncMock(return_value=True)
    return commands


class TestAdminListCommand:
    """Tests for the admin_list command."""

    @pytest.mark.asyncio
    async def test_admin_list_permission_denied(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list denies access to non-admin users."""
        # Mock get_permission_level to return USER level (insufficient for MODERATOR requirement)
        from helpers.permissions_helper import PermissionLevel

        with patch(
            "helpers.decorators.get_permission_level", return_value=PermissionLevel.USER
        ):
            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

        mock_interaction.response.send_message.assert_called_once_with(
            "You don't have permission to use this command.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_admin_list_no_settings_found(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list handles case where target user has no settings."""
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        # Mock fetch_channel_settings to return empty result
        with patch("helpers.voice_settings.fetch_channel_settings") as mock_fetch:
            mock_fetch.return_value = {
                "settings": None,
                "active_channel": None,
                "is_active": False,
                "jtc_channel_id": None,
                "embeds": [],
            }

            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

            mock_interaction.response.defer.assert_called_once()
            mock_interaction.followup.send.assert_called_once()

            args = mock_interaction.followup.send.call_args
            assert "📭 No saved voice channel settings found" in args.args[0]
            assert args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_admin_list_shows_user_settings(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list displays user settings when they exist."""
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        # Create mock embed
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.title = "🔧 Voice Settings for TargetUser"

        # Mock fetch_channel_settings to return settings with embeds
        with patch("helpers.voice_settings.fetch_channel_settings") as mock_fetch:
            mock_fetch.return_value = {
                "settings": {
                    "channel_name": "Custom Channel",
                    "user_limit": 5,
                    "lock": True,
                },
                "active_channel": None,
                "is_active": False,
                "jtc_channel_id": 55555,
                "embeds": [mock_embed],
            }

            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

            # Verify the helper was called correctly
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args
            assert call_args.kwargs["target_user"] == mock_target_user
            assert call_args.kwargs["allow_inactive"] is True

            # Verify embed was sent
            mock_interaction.followup.send.assert_called_once()
            send_args = mock_interaction.followup.send.call_args
            assert send_args.kwargs["embed"] == mock_embed
            assert send_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_admin_list_multiple_jtc_settings(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list handles multiple JTC channel settings."""
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        # Create multiple mock embeds for different JTC channels
        embed1 = MagicMock(spec=discord.Embed)
        embed1.title = "Settings for JTC 1"
        embed2 = MagicMock(spec=discord.Embed)
        embed2.title = "Settings for JTC 2"

        with patch("helpers.voice_settings.fetch_channel_settings") as mock_fetch:
            mock_fetch.return_value = {
                "settings": {"channel_name": "First Channel"},
                "active_channel": None,
                "is_active": False,
                "jtc_channel_id": 55555,
                "embeds": [embed1, embed2],
            }

            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

            # Verify multiple embeds were sent
            assert mock_interaction.followup.send.call_count == 2

    @pytest.mark.asyncio
    async def test_admin_list_handles_errors_gracefully(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list handles errors gracefully."""
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        # Mock fetch_channel_settings to raise an exception
        with (
            patch("helpers.voice_settings.fetch_channel_settings") as mock_fetch,
            patch(
                "helpers.discord_reply.send_user_error",
                new_callable=AsyncMock,
            ) as mock_send_error,
        ):
            mock_fetch.side_effect = Exception("Database error")

            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

            mock_send_error.assert_called_once()
            error_args = mock_send_error.call_args
            assert "❌" in error_args.args[1]
            assert "Something went wrong" in error_args.args[1]

    @pytest.mark.asyncio
    async def test_admin_list_active_channel_with_settings(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list shows active channel settings correctly."""
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        # Mock active channel
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.name = "Active Channel"

        # Create mock embed for active channel
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.title = "🎙️ Active Voice Channel Settings"
        mock_embed.color = discord.Color.green()

        with patch("helpers.voice_settings.fetch_channel_settings") as mock_fetch:
            mock_fetch.return_value = {
                "settings": {
                    "channel_name": "Active Channel",
                    "user_limit": 10,
                    "lock": False,
                },
                "active_channel": mock_channel,
                "is_active": True,
                "jtc_channel_id": 55555,
                "embeds": [mock_embed],
            }

            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

            # Verify the embed was sent
            mock_interaction.followup.send.assert_called_once()
            send_args = mock_interaction.followup.send.call_args
            assert send_args.kwargs["embed"] == mock_embed

    @pytest.mark.asyncio
    async def test_admin_list_fallback_when_no_embeds(
        self, voice_commands, mock_interaction, mock_target_user
    ):
        """Test admin_list fallback when settings exist but no embeds are generated."""
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        with patch("helpers.voice_settings.fetch_channel_settings") as mock_fetch:
            mock_fetch.return_value = {
                "settings": {"channel_name": "Some Channel"},
                "active_channel": None,
                "is_active": False,
                "jtc_channel_id": 55555,
                "embeds": [],  # No embeds generated
            }

            await voice_commands.admin_list.callback(
                voice_commands, mock_interaction, mock_target_user
            )

            # Verify fallback embed was sent
            mock_interaction.followup.send.assert_called_once()
            send_args = mock_interaction.followup.send.call_args

            # Should be an embed parameter, not direct text
            assert "embed" in send_args.kwargs
            assert send_args.kwargs["ephemeral"] is True
