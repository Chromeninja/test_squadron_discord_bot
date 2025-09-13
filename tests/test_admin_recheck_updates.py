"""Additional tests for updated admin recheck announcement functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helpers.announcement import send_admin_recheck_notification


class TestUpdatedAdminRecheckFlow:
    """Tests for the updated admin recheck flow functionality."""

    @pytest.mark.asyncio
    async def test_admin_recheck_no_change_single_message(self):
        """Test that admin recheck with no change sends single message and no bulk enqueue."""
        # Mock config service - patch where it's imported in the function
        with patch("services.config_service.ConfigService") as mock_config_service:
            mock_config_instance = AsyncMock()
            mock_config_service.return_value = mock_config_instance
            mock_config_instance.get_global_setting.return_value = 123456789

            # Mock bot and its components
            mock_bot = MagicMock()
            mock_channel = AsyncMock()
            mock_channel.name = "admin-announcements"
            mock_bot.get_channel.return_value = mock_channel

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
        # Mock config service
        with patch("services.config_service.ConfigService") as mock_config_service:
            mock_config_instance = AsyncMock()
            mock_config_service.return_value = mock_config_instance
            mock_config_instance.get_global_setting.return_value = 123456789

            # Mock bot and its components
            mock_bot = MagicMock()
            mock_channel = AsyncMock()
            mock_channel.name = "admin-announcements"
            mock_bot.get_channel.return_value = mock_channel

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
    async def test_admin_recheck_uses_admin_channel_config(self):
        """Test that admin recheck uses admin_announce_channel_id from config."""
        # Mock config service to return specific admin channel
        admin_channel_id = 999888777
        with patch("services.config_service.ConfigService") as mock_config_service:
            mock_config_instance = AsyncMock()
            mock_config_service.return_value = mock_config_instance
            mock_config_instance.get_global_setting.return_value = admin_channel_id

            # Mock bot - note leadership channel is different
            mock_bot = MagicMock()
            mock_bot.config = {
                "channels": {"leadership_announcement_channel_id": 555444333}
            }

            mock_admin_channel = AsyncMock()
            mock_admin_channel.name = "admin-notifications"
            mock_bot.get_channel.return_value = mock_admin_channel

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

            # Verify the admin channel was requested from config service
            mock_config_instance.get_global_setting.assert_called_once_with(
                "admin_announce_channel_id", None
            )

            # Verify bot.get_channel was called with admin channel ID, not leadership channel
            mock_bot.get_channel.assert_called_once_with(admin_channel_id)

            # Verify message was sent to admin channel
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][0] is mock_admin_channel
