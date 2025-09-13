"""Tests for the modern admin recheck-user command in AdminCog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest
from cogs.admin.commands import AdminCog


class TestModernAdminRecheckUserCommand:
    """Test the recheck_user command in the modern AdminCog."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance with required attributes."""
        bot = AsyncMock()
        bot.config = {"channels": {"leadership_announcement_channel_id": 999999999}}

        # Mock permission check
        async def mock_has_admin_permissions(user):
            return True

        bot.has_admin_permissions = mock_has_admin_permissions

        # Mock get_channel for leadership channel
        mock_channel = AsyncMock()
        bot.get_channel.return_value = mock_channel

        return bot

    @pytest.fixture
    def admin_cog(self, mock_bot):
        """Create AdminCog instance."""
        return AdminCog(mock_bot)

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = AsyncMock(spec=discord.Member)
        member.id = 987654321
        member.display_name = "TestUser"
        member.mention = "<@987654321>"
        return member

    @pytest.fixture
    def mock_interaction(self):
        """Create a mock Discord interaction."""
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.user = AsyncMock(spec=discord.Member)
        interaction.user.id = 123456789
        interaction.user.display_name = "AdminUser"
        interaction.user.send = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_recheck_user_no_change_scenario(
        self, admin_cog, mock_interaction, mock_member
    ):
        """Test recheck when status doesn't change - expect 'No Change' message and no bulk enqueue."""

        # Mock database lookup to return existing verification
        with patch("services.db.database.Database.get_connection") as mock_db:
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = ["TestHandle123"]
            mock_db.return_value.__aenter__.return_value.execute.return_value = (
                mock_cursor
            )

            # Mock snapshot and diff
            with (
                patch("helpers.snapshots.snapshot_member_state"),
                patch("helpers.snapshots.diff_snapshots") as mock_diff,
            ):

                mock_diff.return_value = SimpleNamespace(
                    status_before="main", status_after="main"
                )

                # Mock reverify_member to return no change (same status)
                with patch("helpers.role_helper.reverify_member") as mock_reverify:
                    mock_reverify.return_value = (True, ("main", "main"), None)

                    # Mock flush_tasks
                    with patch("helpers.task_queue.flush_tasks"):

                        # Mock leadership log
                        with patch("helpers.leadership_log.post_if_changed"):

                            # Mock admin notification
                            with patch(
                                "helpers.announcement.send_admin_recheck_notification"
                            ) as mock_admin_notif:
                                mock_admin_notif.return_value = (
                                    True,
                                    False,
                                )  # Success, no change

                                # Mock bulk announcer - should NOT be called for no change
                                with patch(
                                    "helpers.announcement.enqueue_verification_event"
                                ) as mock_bulk_enqueue:

                                    # Execute the command
                                    await admin_cog.recheck_user.callback(
                                        admin_cog, mock_interaction, mock_member
                                    )

                                    # Verify admin notification was sent with correct parameters
                                    mock_admin_notif.assert_called_once_with(
                                        bot=admin_cog.bot,
                                        admin_display_name="AdminUser",
                                        member=mock_member,
                                        old_status="main",
                                        new_status="main",
                                    )

                                    # Verify bulk announcer was NOT called (no status change)
                                    mock_bulk_enqueue.assert_not_called()

                                    # Verify interaction response indicates no change
                                    mock_interaction.followup.send.assert_called_once()
                                    response_call = (
                                        mock_interaction.followup.send.call_args
                                    )
                                    response_msg = response_call[0][0]
                                    assert "no status change" in response_msg.lower()
                                    assert (
                                        "Main" in response_msg
                                    )  # Should show the unchanged status

    @pytest.mark.asyncio
    async def test_recheck_user_status_change_scenario(
        self, admin_cog, mock_interaction, mock_member
    ):
        """Test recheck when status changes - expect 'Updated' message and bulk enqueue called once."""

        # Mock database lookup to return existing verification
        with patch("services.db.database.Database.get_connection") as mock_db:
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = ["TestHandle123"]
            mock_db.return_value.__aenter__.return_value.execute.return_value = (
                mock_cursor
            )

            # Mock snapshot and diff
            with (
                patch("helpers.snapshots.snapshot_member_state"),
                patch("helpers.snapshots.diff_snapshots") as mock_diff,
            ):

                mock_diff.return_value = SimpleNamespace(
                    status_before="affiliate", status_after="main"
                )

                # Mock reverify_member to return status change
                with patch("helpers.role_helper.reverify_member") as mock_reverify:
                    mock_reverify.return_value = (True, ("affiliate", "main"), None)

                    # Mock flush_tasks
                    with patch("helpers.task_queue.flush_tasks"):

                        # Mock leadership log
                        with patch("helpers.leadership_log.post_if_changed"):

                            # Mock admin notification
                            with patch(
                                "helpers.announcement.send_admin_recheck_notification"
                            ) as mock_admin_notif:
                                mock_admin_notif.return_value = (
                                    True,
                                    True,
                                )  # Success, changed

                                # Mock bulk announcer - should be called once for status change
                                with patch(
                                    "helpers.announcement.enqueue_verification_event"
                                ) as mock_bulk_enqueue:

                                    # Execute the command
                                    await admin_cog.recheck_user.callback(
                                        admin_cog, mock_interaction, mock_member
                                    )

                                    # Verify admin notification was sent with correct parameters
                                    mock_admin_notif.assert_called_once_with(
                                        bot=admin_cog.bot,
                                        admin_display_name="AdminUser",
                                        member=mock_member,
                                        old_status="affiliate",
                                        new_status="main",
                                    )

                                    # Verify bulk announcer was called once with correct parameters
                                    mock_bulk_enqueue.assert_called_once_with(
                                        mock_member, "affiliate", "main"
                                    )

                                    # Verify interaction response indicates status change
                                    mock_interaction.followup.send.assert_called_once()
                                    response_call = (
                                        mock_interaction.followup.send.call_args
                                    )
                                    response_msg = response_call[0][0]
                                    assert "status changed" in response_msg.lower()
                                    assert (
                                        "Affiliate" in response_msg
                                        and "Main" in response_msg
                                    )  # Should show both statuses

    @pytest.mark.asyncio
    async def test_recheck_user_unknown_statuses_fallback(
        self, admin_cog, mock_interaction, mock_member
    ):
        """Test recheck with unknown/null statuses - should use 'unknown' fallback."""

        # Mock database lookup to return existing verification
        with patch("services.db.database.Database.get_connection") as mock_db:
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = ["TestHandle123"]
            mock_db.return_value.__aenter__.return_value.execute.return_value = (
                mock_cursor
            )

            # Mock snapshot and diff with None values
            with (
                patch("helpers.snapshots.snapshot_member_state"),
                patch("helpers.snapshots.diff_snapshots") as mock_diff,
            ):

                mock_diff.return_value = SimpleNamespace(
                    status_before=None, status_after=None
                )

                # Mock reverify_member to return unclear status (None values)
                with patch("helpers.role_helper.reverify_member") as mock_reverify:
                    mock_reverify.return_value = (True, None, None)

                    # Mock other dependencies
                    with (
                        patch("helpers.task_queue.flush_tasks"),
                        patch("helpers.leadership_log.post_if_changed"),
                        patch(
                            "helpers.announcement.send_admin_recheck_notification"
                        ) as mock_admin_notif,
                        patch(
                            "helpers.announcement.enqueue_verification_event"
                        ) as mock_bulk_enqueue,
                    ):

                        mock_admin_notif.return_value = (
                            True,
                            False,
                        )  # Success, no change (fallback test)

                        # Execute the command
                        await admin_cog.recheck_user.callback(
                            admin_cog, mock_interaction, mock_member
                        )

                        # Verify admin notification was sent with 'unknown' fallback values
                        mock_admin_notif.assert_called_once_with(
                            bot=admin_cog.bot,
                            admin_display_name="AdminUser",
                            member=mock_member,
                            old_status="unknown",
                            new_status="unknown",
                        )

                        # Verify bulk announcer was NOT called (unknown -> unknown is no change)
                        mock_bulk_enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_recheck_user_permission_denied(
        self, admin_cog, mock_interaction, mock_member
    ):
        """Test recheck when user doesn't have admin permissions."""

        # Mock permission check to return False asynchronously
        async def mock_has_admin_permissions(user):
            return False

        admin_cog.bot.has_admin_permissions = mock_has_admin_permissions

        # Ensure the response.send_message is properly mocked as async
        mock_interaction.response.send_message = AsyncMock()

        # Execute the command
        await admin_cog.recheck_user.callback(admin_cog, mock_interaction, mock_member)

        # Verify permission denied message was sent
        mock_interaction.response.send_message.assert_called_once()
        response_call = mock_interaction.response.send_message.call_args
        assert "don't have permission" in response_call[0][0]
        assert response_call[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_recheck_user_not_verified(
        self, admin_cog, mock_interaction, mock_member
    ):
        """Test recheck when user is not in verification database."""

        # Mock database lookup to return no verification record
        with patch("services.db.database.Database.get_connection") as mock_db:
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = None  # No verification record
            mock_db.return_value.__aenter__.return_value.execute.return_value = (
                mock_cursor
            )

            # Execute the command
            await admin_cog.recheck_user.callback(
                admin_cog, mock_interaction, mock_member
            )

            # Verify "not verified" message was sent
            mock_interaction.followup.send.assert_called_once()
            response_call = mock_interaction.followup.send.call_args
            assert "is not verified" in response_call[0][0]
            assert response_call[1]["ephemeral"] is True
