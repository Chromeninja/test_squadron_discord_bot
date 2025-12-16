"""Tests for the modernized /verify check commands (4-command structure)."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.admin.verify_bulk import VerifyCommands


class TestVerifyCheckCommands:
    """Test the 4 verify check commands: check-user, check-members, check-channel, check-voice."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = MagicMock()
        bot.config = {
            "auto_recheck": {"batch": {"max_users_per_run": 50}},
            "channels": {"leadership_announcement_channel_id": 999999999},
        }
        bot.services.verify_bulk.is_running = MagicMock(return_value=False)
        bot.services.verify_bulk.queue_size = MagicMock(return_value=0)
        bot.services.verify_bulk.enqueue_manual = AsyncMock(return_value="job_123")
        bot.has_admin_permissions = AsyncMock(return_value=True)
        return bot

    @pytest.fixture
    def verify_commands(self, mock_bot):
        """Create VerifyCommands instance."""
        return VerifyCommands(mock_bot)

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = MagicMock(spec=discord.Member)
        member.id = 987654321
        member.display_name = "TestUser"
        member.mention = "<@987654321>"
        return member

    @pytest.fixture
    def mock_interaction(self):
        """Create a mock Discord interaction."""
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild, id=123456789)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.user = MagicMock(spec=discord.Member, id=111111111)
        return interaction

    @pytest.fixture
    def mock_voice_channel(self):
        """Create a mock voice channel."""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 888888888
        channel.name = "General Voice"
        channel.mention = "<#888888888>"
        return channel

    # ========== Tests for /verify check-user ==========

    @pytest.mark.asyncio
    async def test_check_user_enqueues_bulk_job(
        self, verify_commands, mock_interaction, mock_member
    ):
        """Test check-user command enqueues bulk job with RSI verification."""
        await verify_commands.check_user.callback(
            verify_commands,
            mock_interaction,
            member=mock_member,
        )

        verify_commands.bot.services.verify_bulk.enqueue_manual.assert_called_once()
        call_args = verify_commands.bot.services.verify_bulk.enqueue_manual.call_args
        assert call_args.kwargs["recheck_rsi"] is True
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "Starting verification check" in call_args[0][0]

    # ========== Tests for /verify check-members ==========

    @pytest.mark.asyncio
    async def test_check_members_with_valid_input(
        self, verify_commands, mock_interaction, mock_member
    ):
        """Test check-members command with valid member mentions."""
        with patch("cogs.admin.verify_bulk.collect_targets") as mock_collect:
            mock_collect.return_value = [mock_member]

            await verify_commands.check_members.callback(
                verify_commands,
                mock_interaction,
                members="<@987654321>",
            )

            mock_collect.assert_called_once_with(
                "users", mock_interaction.guild, "<@987654321>", None
            )
            verify_commands.bot.services.verify_bulk.enqueue_manual.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_members_empty_string_error(
        self, verify_commands, mock_interaction
    ):
        """Test check-members command rejects empty members parameter."""
        await verify_commands.check_members.callback(
            verify_commands,
            mock_interaction,
            members="",
        )

        call_args = mock_interaction.followup.send.call_args
        assert "At least one member must be specified" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_check_members_no_valid_members_error(
        self, verify_commands, mock_interaction
    ):
        """Test check-members command handles no valid members found."""
        with patch("cogs.admin.verify_bulk.collect_targets") as mock_collect:
            mock_collect.return_value = []

            await verify_commands.check_members.callback(
                verify_commands,
                mock_interaction,
                members="invalid text",
            )

            call_args = mock_interaction.followup.send.call_args
            assert "No valid members found" in call_args[0][0]

    # ========== Tests for /verify check-channel ==========

    @pytest.mark.asyncio
    async def test_check_channel_with_members(
        self, verify_commands, mock_interaction, mock_member, mock_voice_channel
    ):
        """Test check-channel command with members in channel."""
        with patch("cogs.admin.verify_bulk.collect_targets") as mock_collect:
            mock_collect.return_value = [mock_member]

            await verify_commands.check_channel.callback(
                verify_commands,
                mock_interaction,
                channel=mock_voice_channel,
            )

            mock_collect.assert_called_once_with(
                "voice_channel", mock_interaction.guild, None, mock_voice_channel
            )
            verify_commands.bot.services.verify_bulk.enqueue_manual.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_channel_empty_error(
        self, verify_commands, mock_interaction, mock_voice_channel
    ):
        """Test check-channel command handles empty channel."""
        with patch("cogs.admin.verify_bulk.collect_targets") as mock_collect:
            mock_collect.return_value = []

            await verify_commands.check_channel.callback(
                verify_commands,
                mock_interaction,
                channel=mock_voice_channel,
            )

            call_args = mock_interaction.followup.send.call_args
            assert "is empty" in call_args[0][0]

    # ========== Tests for /verify check-voice ==========

    @pytest.mark.asyncio
    async def test_check_voice_with_active_users(
        self, verify_commands, mock_interaction, mock_member
    ):
        """Test check-voice command with users in active voice channels."""
        with patch("cogs.admin.verify_bulk.collect_targets") as mock_collect:
            mock_collect.return_value = [mock_member]

            await verify_commands.check_voice.callback(
                verify_commands,
                mock_interaction,
            )

            mock_collect.assert_called_once_with(
                "active_voice", mock_interaction.guild, None, None
            )
            verify_commands.bot.services.verify_bulk.enqueue_manual.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_voice_no_active_users_error(
        self, verify_commands, mock_interaction
    ):
        """Test check-voice command handles no users in voice channels."""
        with patch("cogs.admin.verify_bulk.collect_targets") as mock_collect:
            mock_collect.return_value = []

            await verify_commands.check_voice.callback(
                verify_commands,
                mock_interaction,
            )

            call_args = mock_interaction.followup.send.call_args
            assert "No members found in any active voice channels" in call_args[0][0]
