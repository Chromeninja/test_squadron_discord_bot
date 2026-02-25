"""
Tests for the /tickets slash commands cog.

Only ``/tickets stats`` remains as a Discord command; all configuration
is now managed via the web dashboard.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import discord

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
    bot.services.ticket = ts

    # ConfigService mock
    cs = AsyncMock()
    cs.get_guild_setting = AsyncMock(return_value=None)
    cs.set_guild_setting = AsyncMock()
    bot.services.config = cs

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
