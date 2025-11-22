"""Additional tests for updated admin recheck announcement functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helpers.announcement import send_admin_recheck_notification


class TestUpdatedAdminRecheckFlow:
    """Tests for the updated admin recheck flow functionality."""

    @pytest.mark.asyncio
    async def test_admin_recheck_no_change_single_message(self):
        """Test that admin recheck with no change sends single message and no bulk enqueue."""
        # Mock bot and its components
        mock_bot = MagicMock()
        mock_channel = AsyncMock()
        mock_channel.name = "admin-announcements"
        mock_bot.get_channel.return_value = mock_channel

        # Mock guild_config service
        mock_guild_config = AsyncMock()
        mock_guild_config.get_channel = AsyncMock(return_value=mock_channel)
        mock_bot.services = MagicMock()
        mock_bot.services.guild_config = mock_guild_config

        # Mock member
        mock_member = MagicMock()
        mock_member.id = 987654321

        # Mock channel_send_message
        with patch(
            "helpers.announcement.channel_send_message", new_callable=AsyncMock
        ) as mock_send:
            result = await send_admin_recheck_notification(
                bot=mock_bot,
                admin_display_name="TestAdmin",
                member=mock_member,
                old_status="main",
                new_status="main",  # No change
            )

            success, changed = result
            assert success is True
            assert changed is False  # No status change
            mock_send.assert_called_once()

            # Verify single-line message for no change
            call_args = mock_send.call_args
            message = call_args[0][1]  # Second arg is message
            assert "[Admin Check • Admin: TestAdmin]" in message
            assert "<@987654321>" in message
            assert "🥺 No changes" in message
            # Should not contain status change line for no change
            assert "Status:" not in message
            assert "\n" not in message  # Should be single line

    @pytest.mark.asyncio
    async def test_admin_recheck_with_change_two_line_message(self):
        """Test that admin recheck with change sends two-line message and enables bulk enqueue."""
        # Mock bot and its components
        mock_bot = MagicMock()
        mock_channel = AsyncMock()
        mock_channel.name = "admin-announcements"
        mock_bot.get_channel.return_value = mock_channel

        # Mock guild_config service
        mock_guild_config = AsyncMock()
        mock_guild_config.get_channel = AsyncMock(return_value=mock_channel)
        mock_bot.services = MagicMock()
        mock_bot.services.guild_config = mock_guild_config

        # Mock member
        mock_member = MagicMock()
        mock_member.id = 987654321

        # Mock channel_send_message
        with patch(
            "helpers.announcement.channel_send_message", new_callable=AsyncMock
        ) as mock_send:
            result = await send_admin_recheck_notification(
                bot=mock_bot,
                admin_display_name="TestAdmin",
                member=mock_member,
                old_status="affiliate",
                new_status="main",  # Status change
            )

            success, changed = result
            assert success is True
            assert changed is True  # Status changed
            mock_send.assert_called_once()

            # Verify two-line message for change
            call_args = mock_send.call_args
            message = call_args[0][1]  # Second arg is message
            assert "[Admin Check • Admin: TestAdmin]" in message
            assert "<@987654321>" in message
            assert "🔁 Updated" in message
            assert "Status: Affiliate → Main" in message
            assert "\n" in message  # Should be two lines

    @pytest.mark.asyncio
    async def test_admin_recheck_uses_leadership_channel_config(self):
        """Test that admin recheck uses leadership_announcement_channel_id from config."""
        # Mock bot with leadership channel configured
        leadership_channel_id = 999888777
        mock_bot = MagicMock()

        mock_leadership_channel = AsyncMock()
        mock_leadership_channel.name = "leadership-logs"
        mock_bot.get_channel.return_value = mock_leadership_channel

        # Mock guild_config service
        mock_guild_config = AsyncMock()
        mock_guild_config.get_channel = AsyncMock(return_value=mock_leadership_channel)
        mock_bot.services = MagicMock()
        mock_bot.services.guild_config = mock_guild_config

        # Mock member
        mock_member = MagicMock()
        mock_member.id = 987654321

        # Mock channel_send_message
        with patch(
            "helpers.announcement.channel_send_message", new_callable=AsyncMock
        ) as mock_send:
            await send_admin_recheck_notification(
                bot=mock_bot,
                admin_display_name="TestAdmin",
                member=mock_member,
                old_status="main",
                new_status="main",
            )

        # Verify guild_config.get_channel was called for leadership channel
        mock_guild_config.get_channel.assert_called()

        # Verify message was sent to leadership channel
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] is mock_leadership_channel
