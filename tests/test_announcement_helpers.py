"""Tests for admin recheck announcement helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helpers.announcement import (
    canonicalize_status_for_display,
    format_admin_recheck_message,
    send_admin_recheck_notification,
)


class TestAdminRecheckHelpers:
    """Test the admin recheck helper functions."""

    def test_canonicalize_status_for_display(self):
        """Test status canonicalization function."""
        # Test main status
        assert canonicalize_status_for_display("main") == "Main"
        assert canonicalize_status_for_display("MAIN") == "Main"
        assert canonicalize_status_for_display(" main ") == "Main"

        # Test affiliate status
        assert canonicalize_status_for_display("affiliate") == "Affiliate"
        assert canonicalize_status_for_display("AFFILIATE") == "Affiliate"
        assert canonicalize_status_for_display(" affiliate ") == "Affiliate"

        # Test non_member status
        assert canonicalize_status_for_display("non_member") == "Not a Member"
        assert canonicalize_status_for_display("NON_MEMBER") == "Not a Member"
        assert canonicalize_status_for_display(" non_member ") == "Not a Member"

        # Test unknown status
        assert canonicalize_status_for_display("unknown") == "Not a Member"
        assert canonicalize_status_for_display("UNKNOWN") == "Not a Member"

        # Test edge cases
        assert canonicalize_status_for_display("") == "Not a Member"
        assert canonicalize_status_for_display(None) == "Not a Member"
        assert canonicalize_status_for_display("invalid") == "Not a Member"

    def test_format_admin_recheck_message_no_change(self):
        """Test admin recheck message formatting with no status change."""
        message = format_admin_recheck_message(
            admin_display_name="TestAdmin",
            user_id=123456789,
            old_status="main",
            new_status="main",
        )

        expected = (
            "[Admin Check • Admin: TestAdmin] <@123456789> 🔁 No Change\n"
            "Status: Main → Main"
        )
        assert message == expected

    def test_format_admin_recheck_message_status_change(self):
        """Test admin recheck message formatting with status change."""
        message, changed = format_admin_recheck_message(
            admin_display_name="AdminUser",
            user_id=987654321,
            old_status="affiliate",
            new_status="main",
        )

        expected = (
            "[Admin Check • Admin: AdminUser] <@987654321> 🔁 Updated\n"
            "Status: Affiliate → Main"
        )
        assert message == expected
        assert changed is True

    def test_format_admin_recheck_message_unknown_to_member(self):
        """Test admin recheck message formatting from unknown to member status."""
        message, changed = format_admin_recheck_message(
            admin_display_name="ModeratorTest",
            user_id=555666777,
            old_status="unknown",
            new_status="non_member",
        )

        expected = (
            "[Admin Check • Admin: ModeratorTest] <@555666777> 🔁 Updated\n"
            "Status: Not a Member → Not a Member"
        )
        assert message == expected
        assert (
            changed is True
        )  # Different internal status values even if display is same

    def test_format_admin_recheck_message_no_change(self):
        """Test format_admin_recheck_message with no status change."""
        message, changed = format_admin_recheck_message(
            admin_display_name="AdminUser",
            user_id=123456789,
            old_status="main",
            new_status="main",
        )

        expected = "[Admin Check • Admin: AdminUser] <@123456789> 🥺 No changes"
        assert message == expected
        assert changed is False

    def test_format_admin_recheck_message_with_change(self):
        """Test format_admin_recheck_message with status change."""
        message, changed = format_admin_recheck_message(
            admin_display_name="AdminUser",
            user_id=123456789,
            old_status="affiliate",
            new_status="main",
        )

        expected = (
            "[Admin Check • Admin: AdminUser] <@123456789> 🔁 Updated\n"
            "Status: Affiliate → Main"
        )
        assert message == expected
        assert changed is True

    @pytest.mark.asyncio
    async def test_send_admin_recheck_notification_success(self):
        """Test successful admin recheck notification sending."""
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
                new_status="main",
            )

            success, changed = result
            assert success is True
            assert changed is True  # Status changed from affiliate to main
            mock_send.assert_called_once()

            # Verify the message content
            call_args = mock_send.call_args
            assert call_args[0][0] is mock_channel  # First arg is channel

            message = call_args[0][1]  # Second arg is message
            assert "[Admin Check • Admin: TestAdmin]" in message
            assert "<@987654321>" in message
            assert "🔁 Updated" in message
            assert "Status: Affiliate → Main" in message

    @pytest.mark.asyncio
    async def test_send_admin_recheck_notification_missing_config(self):
        """Test admin recheck notification with missing channel config."""
        # Mock bot with missing config
        mock_bot = MagicMock()

        # Mock guild_config service to return None
        mock_guild_config = AsyncMock()
        mock_guild_config.get_channel = AsyncMock(return_value=None)
        mock_bot.services = MagicMock()
        mock_bot.services.guild_config = mock_guild_config

        mock_member = MagicMock()
        mock_member.id = 987654321

        result = await send_admin_recheck_notification(
            bot=mock_bot,
            admin_display_name="TestAdmin",
            member=mock_member,
            old_status="main",
            new_status="main",
        )

            success, changed = result
            assert success is False
            assert changed is False

    @pytest.mark.asyncio
    async def test_send_admin_recheck_notification_channel_not_found(self):
        """Test admin recheck notification when channel is not found."""
        # Mock bot with config but channel not found
        mock_bot = MagicMock()
        mock_bot.get_channel.return_value = None  # Channel not found

        # Mock guild_config service to return None (channel not found)
        mock_guild_config = AsyncMock()
        mock_guild_config.get_channel = AsyncMock(return_value=None)
        mock_bot.services = MagicMock()
        mock_bot.services.guild_config = mock_guild_config

        mock_member = MagicMock()
        mock_member.id = 987654321

        result = await send_admin_recheck_notification(
            bot=mock_bot,
            admin_display_name="TestAdmin",
            member=mock_member,
            old_status="main",
            new_status="main",
        )

            success, changed = result
            assert success is False
            assert changed is False
