"""Tests for updated admin recheck announcement functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helpers.announcement import send_admin_recheck_notification


class TestUpdatedAdminRecheckFlow:
    @pytest.mark.asyncio
    async def test_admin_recheck_no_change_single_message(self):
        mock_bot = MagicMock()
        mock_bot.config = {"channels": {"leadership_announcement_channel_id": 123}}
        mock_channel = AsyncMock()
        mock_channel.name = "admin-announcements"
        mock_bot.get_channel.return_value = mock_channel

        mock_member = MagicMock()
        mock_member.id = 42

        with patch("helpers.announcement.channel_send_message", new_callable=AsyncMock) as mock_send:
            result = await send_admin_recheck_notification(
                bot=mock_bot,
                admin_display_name="AdminOne",
                member=mock_member,
                old_status="main",
                new_status="main",
            )

        success, changed = result
        assert success is True
        assert changed is False
        mock_send.assert_called_once()

        message = mock_send.call_args[0][1]
        assert "[Admin Check • Admin: AdminOne]" in message
        assert "<@42>" in message
        assert "No changes" in message

    @pytest.mark.asyncio
    async def test_admin_recheck_with_change_two_line_message(self):
        mock_bot = MagicMock()
        mock_bot.config = {"channels": {"leadership_announcement_channel_id": 123}}
        mock_channel = AsyncMock()
        mock_channel.name = "admin-announcements"
        mock_bot.get_channel.return_value = mock_channel

        mock_member = MagicMock()
        mock_member.id = 99

        with patch("helpers.announcement.channel_send_message", new_callable=AsyncMock) as mock_send:
            result = await send_admin_recheck_notification(
                bot=mock_bot,
                admin_display_name="AdminTwo",
                member=mock_member,
                old_status="affiliate",
                new_status="main",
            )

        success, changed = result
        assert success is True
        assert changed is True
        mock_send.assert_called_once()

        message = mock_send.call_args[0][1]
        assert "[Admin Check • Admin: AdminTwo]" in message
        assert "<@99>" in message
        assert "Updated" in message
        assert "Status:" in message

    @pytest.mark.asyncio
    async def test_admin_recheck_uses_leadership_channel_config(self):
        admin_channel_id = 555444333
        mock_bot = MagicMock()
        mock_bot.config = {"channels": {"leadership_announcement_channel_id": admin_channel_id}}

        mock_admin_channel = AsyncMock()
        mock_admin_channel.name = "admin-notifications"
        mock_bot.get_channel.return_value = mock_admin_channel

        mock_member = MagicMock()
        mock_member.id = 7

        with patch("helpers.announcement.channel_send_message", new_callable=AsyncMock) as mock_send:
            await send_admin_recheck_notification(
                bot=mock_bot,
                admin_display_name="AdminThree",
                member=mock_member,
                old_status="main",
                new_status="main",
            )

        mock_bot.get_channel.assert_called_once_with(admin_channel_id)
        mock_send.assert_called_once()
