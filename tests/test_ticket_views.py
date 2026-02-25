"""
Tests for ticket Discord UI views — TicketPanelView and TicketControlView.

Uses FakeInteraction / mock_bot from conftest and mocks the service layer.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

import discord

from helpers.ticket_views import (
    TicketCategorySelect,
    TicketControlView,
    TicketPanelView,
    _create_ticket_thread,
    _log_ticket_event,
)
from tests.conftest import FakeInteraction, FakeUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_bot_with_services(
    *,
    categories: list | None = None,
    rate_allowed: bool = True,
    cooldown: int = 0,
    ticket_id: int | None = 1,
    ticket: dict | None = None,
    staff_roles: str = "[]",
    close_message: str = "Closed.",
    log_channel_id: str | None = None,
) -> MagicMock:
    """Build a mock bot with .services.ticket and .services.config stubs."""
    bot = MagicMock()

    # TicketService
    ts = AsyncMock()
    ts.get_categories = AsyncMock(return_value=categories or [])
    ts.check_rate_limit = AsyncMock(return_value=rate_allowed)
    ts.get_cooldown_remaining = AsyncMock(return_value=cooldown)
    ts.create_ticket = AsyncMock(return_value=ticket_id)
    ts.get_ticket_by_thread = AsyncMock(return_value=ticket)
    ts.close_ticket_by_thread = AsyncMock(return_value=True)
    bot.services.ticket = ts

    # ConfigService
    cs = AsyncMock()

    async def _guild_setting(guild_id, key, default=None):
        mapping = {
            "tickets.staff_roles": staff_roles,
            "tickets.close_message": close_message,
            "tickets.log_channel_id": log_channel_id,
            "tickets.default_welcome_message": "Welcome!",
        }
        return mapping.get(key, default)

    cs.get_guild_setting = AsyncMock(side_effect=_guild_setting)
    bot.services.config = cs

    bot.get_channel = MagicMock(return_value=None)

    return bot


# ---------------------------------------------------------------------------
# TicketPanelView
# ---------------------------------------------------------------------------


class TestTicketPanelView:
    """Tests for the panel 'Create Ticket' button callback."""

    @pytest.mark.asyncio
    async def test_view_has_button(self) -> None:
        """Panel view should contain exactly one button with the right custom_id."""
        bot = _mock_bot_with_services()
        view = TicketPanelView(bot)
        assert len(view.children) == 1
        btn = view.children[0]
        assert btn.custom_id == "ticket_create_button"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_create_ticket_no_guild(self) -> None:
        """Button click outside a guild sends an error."""
        bot = _mock_bot_with_services()
        view = TicketPanelView(bot)
        interaction = FakeInteraction()
        interaction.guild = None  # no guild context

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_create_ticket_rate_limited(self) -> None:
        """When the user is rate-limited, they receive a cooldown message."""
        bot = _mock_bot_with_services(rate_allowed=False, cooldown=120)
        view = TicketPanelView(bot)
        interaction = FakeInteraction()

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_create_ticket_no_categories(self) -> None:
        """With no categories, defer + call _create_ticket_thread directly."""
        bot = _mock_bot_with_services(categories=[])
        view = TicketPanelView(bot)
        interaction = FakeInteraction()

        with patch("helpers.ticket_views._create_ticket_thread", new_callable=AsyncMock) as mock_create:
            await view._on_create_ticket(interaction)  # type: ignore[arg-type]
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_ticket_with_categories(self) -> None:
        """With categories, respond with a select menu."""
        cats = [{"id": 1, "name": "Support", "description": "Help", "emoji": None}]
        bot = _mock_bot_with_services(categories=cats)
        view = TicketPanelView(bot)
        interaction = FakeInteraction()

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        # response.send_message should have been called (ephemeral select)
        assert interaction.response._is_done


# ---------------------------------------------------------------------------
# TicketCategorySelect
# ---------------------------------------------------------------------------


class TestTicketCategorySelect:
    """Tests for the category dropdown."""

    def test_options_built_correctly(self) -> None:
        """Select options match the provided categories."""
        cats = [
            {"id": 1, "name": "General", "description": "General help", "emoji": "📩"},
            {"id": 2, "name": "Billing", "description": "Payment issues", "emoji": None},
        ]
        bot = _mock_bot_with_services()
        select = TicketCategorySelect(bot, cats)
        assert len(select.options) == 2
        assert select.options[0].label == "General"
        assert select.options[1].label == "Billing"

    @pytest.mark.asyncio
    async def test_callback_triggers_thread_creation(self) -> None:
        """Selecting a category calls _create_ticket_thread."""
        cats = [{"id": 5, "name": "Bugs", "description": "", "emoji": None}]
        bot = _mock_bot_with_services()
        select = TicketCategorySelect(bot, cats)
        select._values = ["5"]  # simulate user selection

        interaction = FakeInteraction()

        with patch("helpers.ticket_views._create_ticket_thread", new_callable=AsyncMock) as mock_create:
            # Monkey-patch values property
            type(select).values = property(lambda self: self._values)  # type: ignore[assignment]
            await select.callback(interaction)  # type: ignore[arg-type]
            mock_create.assert_awaited_once()


# ---------------------------------------------------------------------------
# TicketControlView
# ---------------------------------------------------------------------------


class TestTicketControlView:
    """Tests for the 'Close Ticket' button callback."""

    @pytest.mark.asyncio
    async def test_view_has_close_button(self) -> None:
        """Control view has a single button with the correct custom_id."""
        bot = _mock_bot_with_services()
        view = TicketControlView(bot)
        assert len(view.children) == 1
        assert view.children[0].custom_id == "ticket_close_button"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_close_no_guild(self) -> None:
        """Close button outside a guild sends an error."""
        bot = _mock_bot_with_services()
        view = TicketControlView(bot)
        interaction = FakeInteraction()
        interaction.guild = None
        interaction.channel = MagicMock()

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_close_not_in_thread(self) -> None:
        """Close button outside a thread sends an error."""
        bot = _mock_bot_with_services()
        view = TicketControlView(bot)
        interaction = FakeInteraction()
        interaction.channel = MagicMock(spec=discord.TextChannel)

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_close_ticket_not_found(self) -> None:
        """If DB has no ticket for this thread, report error."""
        bot = _mock_bot_with_services(ticket=None)
        view = TicketControlView(bot)
        interaction = FakeInteraction()
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        interaction.channel = thread

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_close_ticket_unauthorized(self) -> None:
        """A non-creator, non-staff user cannot close the ticket."""
        ticket = {
            "id": 1,
            "user_id": 999,  # different from interaction user
            "guild_id": 123,
        }
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketControlView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 1  # not the creator
        user.roles = []
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        interaction.channel = thread

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_close_ticket_creator_allowed(self) -> None:
        """The ticket creator can close the ticket."""
        ticket = {
            "id": 1,
            "user_id": 42,
            "guild_id": 123,
        }
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketControlView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 42  # same as ticket creator
        user.roles = []
        user.mention = "@creator"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.send = AsyncMock()
        thread.edit = AsyncMock()
        thread.mention = "#ticket-thread"
        interaction.channel = thread

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        bot.services.ticket.close_ticket_by_thread.assert_awaited_once()


# ---------------------------------------------------------------------------
# _create_ticket_thread
# ---------------------------------------------------------------------------


class TestCreateTicketThread:
    """Tests for ticket thread creation helper."""

    @pytest.mark.asyncio
    async def test_thread_is_renamed_to_ticket_number(self) -> None:
        """Created thread is renamed to use the generated ticket number."""
        bot = _mock_bot_with_services(ticket_id=123)

        interaction = FakeInteraction(user=FakeUser(user_id=42, display_name="Pilot"))
        text_channel = MagicMock(spec=discord.TextChannel)
        text_channel.id = 777
        thread = MagicMock(spec=discord.Thread)
        thread.id = 888
        thread.add_user = AsyncMock()
        thread.send = AsyncMock()
        thread.edit = AsyncMock()
        thread.mention = "#ticket-123"
        text_channel.create_thread = AsyncMock(return_value=thread)
        interaction.channel = text_channel

        await _create_ticket_thread(bot, interaction, category=None)  # type: ignore[arg-type]

        thread.edit.assert_any_await(name="ticket-123")


# ---------------------------------------------------------------------------
# _log_ticket_event
# ---------------------------------------------------------------------------


class TestLogTicketEvent:
    """Tests for the log channel helper."""

    @pytest.mark.asyncio
    async def test_no_log_channel_configured(self) -> None:
        """Silently returns when no log channel is set."""
        bot = _mock_bot_with_services(log_channel_id=None)
        # Should not raise
        await _log_ticket_event(bot, 123, title="Test", description="desc", color=0)

    @pytest.mark.asyncio
    async def test_log_channel_sends_embed(self) -> None:
        """When a log channel is configured, an embed is sent."""
        bot = _mock_bot_with_services(log_channel_id="456")
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=channel)

        await _log_ticket_event(bot, 123, title="Test", description="desc", color=0)
        channel.send.assert_awaited_once()
