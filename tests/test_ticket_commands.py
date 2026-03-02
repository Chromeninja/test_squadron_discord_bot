"""
Tests for the /tickets slash commands cog.

Covers ``/tickets stats``, ``/tickets health``, and ``/tickets cleanup``
Discord commands; all configuration is managed via the web dashboard.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.permissions_helper import PermissionLevel

# ---------------------------------------------------------------------------
# Auto-patch the permission decorator so commands execute in tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _bypass_permission_check():
    """Patch get_permission_level so the decorator always grants access."""
    with patch(
        "helpers.decorators.get_permission_level",
        new_callable=AsyncMock,
        return_value=PermissionLevel.BOT_OWNER,
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot() -> MagicMock:
    """Create a minimal mock bot for TicketCommands."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.guilds = []

    # TicketService mock
    ts = AsyncMock()
    ts.get_categories = AsyncMock(return_value=[])
    ts.create_category = AsyncMock(return_value=1)
    ts.delete_category = AsyncMock(return_value=True)
    ts.get_ticket_stats = AsyncMock(return_value={"open": 2, "closed": 5, "total": 7})
    ts.get_thread_health = AsyncMock(
        return_value={
            "active": 2,
            "archived": 5,
            "deleted": 0,
            "total_threads": 7,
            "limit": 1000,
            "usage_pct": 0.7,
            "status": "healthy",
        }
    )
    ts.get_oldest_closed_tickets = AsyncMock(return_value=[])
    ts.get_cleanup_candidates = AsyncMock(return_value=[])
    ts.mark_thread_deleted = AsyncMock(return_value=True)
    bot.services.ticket = ts

    # ConfigService mock
    cs = AsyncMock()
    cs.get_guild_setting = AsyncMock(return_value=None)
    cs.set_guild_setting = AsyncMock()
    bot.services.config = cs

    # GuildConfigHelper mock
    gc = AsyncMock()
    gc.get_admin_roles = AsyncMock(return_value=[])
    bot.services.guild_config = gc

    return bot


def _interaction_with_guild(guild_id: int = 123) -> MagicMock:
    """Create a mock Interaction with discord.Member user and proper guild."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 99999
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.guild.name = "TestGuild"
    interaction.guild.get_channel = MagicMock(return_value=None)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTicketCommandsStats:
    """Tests for /tickets stats — the only remaining Discord command."""

    @pytest.mark.asyncio
    async def test_stats_returns_embed(self) -> None:
        """Stats command should send an embed with ticket counts."""
        bot = _make_bot()

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        await cog.stats.callback(cog, interaction)  # type: ignore[call-arg]

        interaction.followup.send.assert_awaited_once()
        call_kwargs = interaction.followup.send.call_args.kwargs
        assert "embed" in call_kwargs

    @pytest.mark.asyncio
    async def test_stats_embed_contains_counts(self) -> None:
        """The stats embed description should include the numeric counts."""
        bot = _make_bot()

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        await cog.stats.callback(cog, interaction)  # type: ignore[call-arg]

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "2" in embed.description  # open
        assert "5" in embed.description  # closed
        assert "7" in embed.description  # total

    @pytest.mark.asyncio
    async def test_stats_includes_thread_count(self) -> None:
        """Stats embed should include thread usage line."""
        bot = _make_bot()

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        await cog.stats.callback(cog, interaction)  # type: ignore[call-arg]

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "1000" in embed.description  # thread limit shown
        assert "Discord Threads" in embed.description


class TestTicketCommandsHealth:
    """Tests for /tickets health."""

    @pytest.mark.asyncio
    async def test_health_returns_embed(self) -> None:
        """Health command should send an embed with status info."""
        bot = _make_bot()

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        await cog.health.callback(cog, interaction)  # type: ignore[call-arg]

        interaction.followup.send.assert_awaited_once()
        call_kwargs = interaction.followup.send.call_args.kwargs
        assert "embed" in call_kwargs

    @pytest.mark.asyncio
    async def test_health_shows_status(self) -> None:
        """Health embed should include the status label."""
        bot = _make_bot()

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        await cog.health.callback(cog, interaction)  # type: ignore[call-arg]

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "HEALTHY" in embed.description


class TestTicketCommandsCleanup:
    """Tests for /tickets cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_dry_run_no_candidates(self) -> None:
        """Dry run with no candidates returns 'nothing to do'."""
        bot = _make_bot()
        bot.services.ticket.get_cleanup_candidates = AsyncMock(return_value=[])

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        cleanup_callback: Any = cog.cleanup.callback
        await cleanup_callback(cog, interaction, older_than=90, dry_run=True)

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "Nothing to do" in embed.title

    @pytest.mark.asyncio
    async def test_cleanup_dry_run_with_candidates(self) -> None:
        """Dry run with candidates shows preview list."""
        bot = _make_bot()
        bot.services.ticket.get_cleanup_candidates = AsyncMock(
            return_value=[
                {
                    "thread_id": 50001,
                    "closed_at": int(time.time()) - (60 * 86400),
                },
            ]
        )

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        cleanup_callback: Any = cog.cleanup.callback
        await cleanup_callback(cog, interaction, older_than=30, dry_run=True)

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "Dry Run" in embed.title
        assert "50001" in embed.description

    @pytest.mark.asyncio
    async def test_cleanup_actual_delete(self) -> None:
        """Non-dry-run cleanup deletes threads and marks them."""
        bot = _make_bot()
        mock_thread = AsyncMock()
        mock_thread.delete = AsyncMock()
        guild_mock = _interaction_with_guild().guild
        guild_mock.get_thread = MagicMock(return_value=mock_thread)

        bot.services.ticket.get_cleanup_candidates = AsyncMock(
            return_value=[
                {
                    "thread_id": 51001,
                    "closed_at": int(time.time()) - (60 * 86400),
                },
            ]
        )

        with (
            patch("cogs.tickets.commands.spawn"),
            patch(
                "cogs.tickets.commands.resolve_leadership_channel",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        interaction = _interaction_with_guild()
        interaction.guild = guild_mock
        cleanup_callback: Any = cog.cleanup.callback
        await cleanup_callback(cog, interaction, older_than=30, dry_run=False)

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "Complete" in embed.title
        bot.services.ticket.mark_thread_deleted.assert_awaited_once_with(51001)


class TestThreadHealthCheckTask:
    """Tests for the background _thread_health_check_task."""

    @pytest.mark.asyncio
    async def test_healthy_status_does_not_alert(self) -> None:
        """No alert is sent when all guilds are healthy."""
        bot = _make_bot()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "TestGuild"
        bot.guilds = [guild]

        with patch("cogs.tickets.commands.spawn"):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

        # Run the task body
        await cog._thread_health_check_task.coro(cog)  # type: ignore[union-attr]

        # No alert level should be stored
        assert guild.id not in cog._last_alert_level

    @pytest.mark.asyncio
    async def test_warning_status_sends_alert(self) -> None:
        """Warning status triggers an alert to the leadership channel."""
        bot = _make_bot()
        bot.services.ticket.get_thread_health = AsyncMock(
            return_value={
                "active": 50,
                "archived": 860,
                "deleted": 0,
                "total_threads": 910,
                "limit": 1000,
                "usage_pct": 91.0,
                "status": "warning",
            }
        )
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "TestGuild"
        bot.guilds = [guild]

        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        with (
            patch("cogs.tickets.commands.spawn"),
            patch(
                "cogs.tickets.commands.resolve_leadership_channel",
                new_callable=AsyncMock,
                return_value=mock_channel,
            ),
        ):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)
            await cog._thread_health_check_task.coro(cog)  # type: ignore[union-attr]

            mock_channel.send.assert_awaited_once()
            assert cog._last_alert_level[guild.id] == "warning"

    @pytest.mark.asyncio
    async def test_duplicate_alert_not_sent(self) -> None:
        """Same severity level does not trigger a second alert."""
        bot = _make_bot()
        bot.services.ticket.get_thread_health = AsyncMock(
            return_value={
                "active": 50,
                "archived": 860,
                "deleted": 0,
                "total_threads": 910,
                "limit": 1000,
                "usage_pct": 91.0,
                "status": "warning",
            }
        )
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "TestGuild"
        bot.guilds = [guild]

        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        with (
            patch("cogs.tickets.commands.spawn"),
            patch(
                "cogs.tickets.commands.resolve_leadership_channel",
                new_callable=AsyncMock,
                return_value=mock_channel,
            ),
        ):
            from cogs.tickets.commands import TicketCommands

            cog = TicketCommands(bot)

            # First run — alert sent
            await cog._thread_health_check_task.coro(cog)  # type: ignore[union-attr]
            assert mock_channel.send.await_count == 1

            # Second run — same level, no new alert
            await cog._thread_health_check_task.coro(cog)  # type: ignore[union-attr]
            assert mock_channel.send.await_count == 1  # still 1
