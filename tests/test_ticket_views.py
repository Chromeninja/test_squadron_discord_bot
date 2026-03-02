"""
Tests for ticket Discord UI views — TicketPanelView and TicketActionView.

Uses FakeInteraction / mock_bot from conftest and mocks the service layer.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import discord
import pytest
from discord.ui import Button

from helpers.ticket_views import (
    TicketActionView,
    TicketCategorySelect,
    TicketCloseReasonModal,
    TicketDescriptionModal,
    TicketPanelView,
    _close_ticket,
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
    channel_categories: list | None = None,
    rate_allowed: bool = True,
    cooldown: int = 0,
    ticket_id: int | None = 1,
    ticket: dict | None = None,
    staff_roles: str = "[]",
    close_message: str = "Closed.",
    log_channel_id: str | None = None,
    max_open_allowed: bool = True,
) -> MagicMock:
    """Build a mock bot with .services.ticket and .services.config stubs."""
    bot = MagicMock()

    # TicketService
    ts = AsyncMock()
    ts.get_categories = AsyncMock(return_value=categories or [])
    ts.get_categories_for_channel = AsyncMock(
        return_value=channel_categories if channel_categories is not None else []
    )
    ts.check_rate_limit = AsyncMock(return_value=rate_allowed)
    ts.get_cooldown_remaining = AsyncMock(return_value=cooldown)
    ts.create_ticket = AsyncMock(return_value=ticket_id)
    ts.get_ticket_by_thread = AsyncMock(return_value=ticket)
    ts.get_category = AsyncMock(return_value=None)
    ts.close_ticket_by_thread = AsyncMock(return_value=True)
    ts.check_max_open_tickets = AsyncMock(return_value=max_open_allowed)
    ts.claim_ticket = AsyncMock(return_value=True)
    ts.unclaim_ticket = AsyncMock(return_value=True)
    ts.reopen_ticket = AsyncMock(return_value=True)
    ts.can_reopen = AsyncMock(return_value=True)
    bot.services.ticket = ts

    # TicketFormService — default to "no form" so legacy flow is used
    tfs = AsyncMock()
    tfs.has_form = AsyncMock(return_value=False)
    bot.services.ticket_form = tfs

    # ConfigService
    cs = AsyncMock()

    async def _guild_setting(guild_id, key, default=None):
        mapping = {
            "tickets.staff_roles": staff_roles,
            "tickets.close_message": close_message,
            "tickets.log_channel_id": log_channel_id,
            "tickets.default_welcome_message": "Welcome!",
            "tickets.max_open_per_user": "5",
            "tickets.reopen_window_hours": "48",
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
    async def test_view_has_public_button_when_enabled(self) -> None:
        """Panel view includes a second public-ticket button when enabled."""
        bot = _mock_bot_with_services()
        view = TicketPanelView(
            bot,
            enable_public_button=True,
            public_button_text="Open Public Ticket",
            public_button_emoji="🌍",
        )
        assert len(view.children) == 2
        custom_ids = {c.custom_id for c in view.children}  # type: ignore[attr-defined]
        assert "ticket_create_button" in custom_ids
        assert "ticket_create_public_button" in custom_ids

    @pytest.mark.asyncio
    async def test_button_order_private_first(self) -> None:
        """Buttons appear in private-first order by default."""
        bot = _mock_bot_with_services()
        view = TicketPanelView(
            bot,
            enable_public_button=True,
            button_order="private_first",
        )
        assert len(view.children) == 2
        assert view.children[0].custom_id == "ticket_create_button"  # type: ignore[attr-defined]
        assert view.children[1].custom_id == "ticket_create_public_button"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_button_order_public_first(self) -> None:
        """Buttons appear in public-first order when specified."""
        bot = _mock_bot_with_services()
        view = TicketPanelView(
            bot,
            enable_public_button=True,
            button_order="public_first",
        )
        assert len(view.children) == 2
        assert view.children[0].custom_id == "ticket_create_public_button"  # type: ignore[attr-defined]
        assert view.children[1].custom_id == "ticket_create_button"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_button_color_mapping(self) -> None:
        """Button colors map to Discord button styles."""
        bot = _mock_bot_with_services()
        view = TicketPanelView(
            bot,
            private_button_color="3BA55D",  # Green -> Success
            enable_public_button=True,
            public_button_color="ED4245",  # Red -> Danger
        )
        import discord
        private_btn = view.children[0]  # type: ignore[attr-defined]
        public_btn = view.children[1]  # type: ignore[attr-defined]
        assert private_btn.style == discord.ButtonStyle.success  # type: ignore[attr-defined]
        assert public_btn.style == discord.ButtonStyle.danger  # type: ignore[attr-defined]

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
        """With no categories, send a description modal."""
        bot = _mock_bot_with_services(categories=[])
        view = TicketPanelView(bot)
        interaction = FakeInteraction()

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        # The response should have sent a modal
        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None
        assert isinstance(interaction.response.sent_modal, TicketDescriptionModal)

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

    @pytest.mark.asyncio
    async def test_create_ticket_channel_filtered_categories(self) -> None:
        """Panel click uses channel-specific categories when available."""
        chan_cats = [
            {"id": 10, "name": "Chan-A Only", "description": "", "emoji": None}
        ]
        all_cats = [
            {"id": 10, "name": "Chan-A Only", "description": "", "emoji": None},
            {"id": 20, "name": "Chan-B Only", "description": "", "emoji": None},
        ]
        bot = _mock_bot_with_services(
            categories=all_cats, channel_categories=chan_cats
        )
        view = TicketPanelView(bot)
        interaction = FakeInteraction()
        interaction.channel_id = 8001  # panel channel

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done
        # Should have called get_categories_for_channel with the panel channel
        bot.services.ticket.get_categories_for_channel.assert_called_once_with(
            interaction.guild.id, 8001  # type: ignore[union-attr]
        )

    @pytest.mark.asyncio
    async def test_create_ticket_falls_back_to_all_categories(self) -> None:
        """When channel has no categories, falls back to all guild categories."""
        all_cats = [
            {"id": 1, "name": "General", "description": "", "emoji": None}
        ]
        # channel_categories is empty → triggers fallback
        bot = _mock_bot_with_services(categories=all_cats, channel_categories=[])
        view = TicketPanelView(bot)
        interaction = FakeInteraction()
        interaction.channel_id = 9999

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done
        # Fallback: get_categories should be called after empty channel result
        bot.services.ticket.get_categories.assert_called_once()


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
        """Selecting a category sends a description modal."""
        cats = [{"id": 5, "name": "Bugs", "description": "", "emoji": None}]
        bot = _mock_bot_with_services()
        select = TicketCategorySelect(bot, cats)
        select._values = ["5"]  # simulate user selection

        interaction = FakeInteraction()

        # Monkey-patch values property
        type(select).values = property(lambda self: self._values)  # type: ignore[assignment]
        await select.callback(interaction)  # type: ignore[arg-type]
        # Should send a description modal
        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None
        assert isinstance(interaction.response.sent_modal, TicketDescriptionModal)

    @pytest.mark.asyncio
    async def test_callback_blocks_when_category_requires_org_main(
        self,
    ) -> None:
        """A non-eligible user is blocked when selecting a restricted category."""
        cats = [
            {
                "id": 9,
                "name": "Main Org",
                "description": "",
                "emoji": None,
                "allowed_statuses": ["org_main"],
            }
        ]
        bot = _mock_bot_with_services()
        select = TicketCategorySelect(bot, cats)
        select._values = ["9"]
        interaction = FakeInteraction()

        type(select).values = property(lambda self: self._values)  # type: ignore[assignment]
        with patch(
            "helpers.ticket_views.Database.get_global_verification_state",
            new=AsyncMock(return_value=None),
        ):
            await select.callback(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert interaction.response.sent_modal is None

    @pytest.mark.asyncio
    async def test_callback_allows_when_category_requires_bot_verified(
        self,
    ) -> None:
        """A verified user can select a category requiring bot_verified."""
        cats = [
            {
                "id": 10,
                "name": "Verified",
                "description": "",
                "emoji": None,
                "allowed_statuses": ["bot_verified"],
            }
        ]
        bot = _mock_bot_with_services()
        select = TicketCategorySelect(bot, cats)
        select._values = ["10"]
        interaction = FakeInteraction()

        type(select).values = property(lambda self: self._values)  # type: ignore[assignment]
        with patch(
            "helpers.ticket_views.Database.get_global_verification_state",
            new=AsyncMock(
                return_value={
                    "rsi_handle": "pilot",
                    "main_orgs": [],
                    "affiliate_orgs": [],
                    "community_moniker": None,
                    "last_updated": 0,
                }
            ),
        ):
            await select.callback(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None
        assert isinstance(interaction.response.sent_modal, TicketDescriptionModal)


# ---------------------------------------------------------------------------
# TicketActionView
# ---------------------------------------------------------------------------


class TestTicketActionView:
    """Tests for the 'Close Ticket' button callback."""

    @pytest.mark.asyncio
    async def test_view_has_action_buttons_and_open_state(self) -> None:
        """Action view has all buttons and open-state disabled rules."""
        bot = _mock_bot_with_services()
        view = TicketActionView(bot)
        assert len(view.children) == 4
        custom_ids = {c.custom_id for c in view.children}  # type: ignore[attr-defined]
        assert "ticket_action_close_button" in custom_ids
        assert "ticket_action_claim_button" in custom_ids
        assert "ticket_action_reopen_button" in custom_ids
        assert "ticket_action_delete_button" in custom_ids

        button_map = {
            button.custom_id: button
            for item in view.children
            if isinstance(item, Button)
            for button in [cast("Button[TicketActionView]", item)]
        }
        assert button_map["ticket_action_claim_button"].disabled is False
        assert button_map["ticket_action_close_button"].disabled is False
        assert button_map["ticket_action_reopen_button"].disabled is True
        assert button_map["ticket_action_delete_button"].disabled is False

    @pytest.mark.asyncio
    async def test_view_closed_state_disables_claim_and_close(self) -> None:
        """Closed-state action view disables claim/close and enables reopen."""
        bot = _mock_bot_with_services()
        view = TicketActionView(bot, ticket_is_closed=True, reopen_enabled=True)
        button_map = {
            button.custom_id: button
            for item in view.children
            if isinstance(item, Button)
            for button in [cast("Button[TicketActionView]", item)]
        }

        assert button_map["ticket_action_claim_button"].disabled is True
        assert button_map["ticket_action_close_button"].disabled is True
        assert button_map["ticket_action_reopen_button"].disabled is False
        assert button_map["ticket_action_delete_button"].disabled is False

    @pytest.mark.asyncio
    async def test_close_no_guild(self) -> None:
        """Close button outside a guild sends an error."""
        bot = _mock_bot_with_services()
        view = TicketActionView(bot)
        interaction = FakeInteraction()
        interaction.guild = None
        interaction.channel = MagicMock()

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_close_not_in_thread(self) -> None:
        """Close button outside a thread sends an error."""
        bot = _mock_bot_with_services()
        view = TicketActionView(bot)
        interaction = FakeInteraction()
        interaction.channel = MagicMock(spec=discord.TextChannel)

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_close_ticket_not_found(self) -> None:
        """If DB has no ticket for this thread, report error."""
        bot = _mock_bot_with_services(ticket=None)
        view = TicketActionView(bot)
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
        view = TicketActionView(bot)

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
        """The ticket creator can close the ticket — shows close reason modal."""
        ticket = {
            "id": 1,
            "user_id": 42,
            "guild_id": 123,
        }
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

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
        # Should send a close-reason modal
        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None
        assert isinstance(interaction.response.sent_modal, TicketCloseReasonModal)

    @pytest.mark.asyncio
    async def test_close_ticket_category_role_allowed(self) -> None:
        """A user with a category Notified Role can close the ticket."""
        ticket = {
            "id": 1,
            "user_id": 42,
            "guild_id": 123,
            "category_id": 5,
        }
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        bot.services.ticket.get_category = AsyncMock(
            return_value={"id": 5, "role_ids": [777]}
        )
        view = TicketActionView(bot)

        role = SimpleNamespace(id=777)
        user = MagicMock(spec=discord.Member)
        user.id = 100
        user.roles = [role]
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        interaction.channel = thread

        await view._on_close_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None
        assert isinstance(interaction.response.sent_modal, TicketCloseReasonModal)


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

        thread.edit.assert_any_await(name="T:123 - ticket - Pilot")

    @pytest.mark.asyncio
    async def test_public_ticket_uses_public_thread_type(self) -> None:
        """Public ticket path creates a public thread in the same channel."""
        bot = _mock_bot_with_services(ticket_id=123)

        interaction = FakeInteraction(user=FakeUser(user_id=42, display_name="Pilot"))
        text_channel = MagicMock(spec=discord.TextChannel)
        text_channel.id = 777
        thread = MagicMock(spec=discord.Thread)
        thread.id = 889
        thread.add_user = AsyncMock()
        thread.send = AsyncMock()
        thread.edit = AsyncMock()
        thread.mention = "#ticket-123"
        text_channel.create_thread = AsyncMock(return_value=thread)
        interaction.channel = text_channel

        await _create_ticket_thread(
            bot,
            cast("discord.Interaction", interaction),
            category=None,
            is_public=True,
        )

        kwargs = text_channel.create_thread.await_args.kwargs
        assert kwargs["type"] == discord.ChannelType.public_thread

    @pytest.mark.asyncio
    async def test_category_mentions_override_global_staff_mentions(self) -> None:
        """When category roles are set, only category roles are mentioned."""
        bot = _mock_bot_with_services(ticket_id=123, staff_roles="[888]")

        interaction = FakeInteraction(user=FakeUser(user_id=42, display_name="Pilot"))
        role_category = SimpleNamespace(id=777, mention="@cat-role")
        role_global = SimpleNamespace(id=888, mention="@global-role")
        guild = SimpleNamespace(
            id=123,
            name="TestGuild",
            get_role=lambda rid: {777: role_category, 888: role_global}.get(rid),
        )
        interaction.guild = guild

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

        category = {"id": 5, "name": "Support", "role_ids": [777]}
        await _create_ticket_thread(bot, interaction, category=category)  # type: ignore[arg-type]

        assert call("@cat-role") in thread.send.await_args_list
        assert call("@global-role") not in thread.send.await_args_list


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


# ---------------------------------------------------------------------------
# TicketPanelView — max open tickets
# ---------------------------------------------------------------------------


class TestTicketPanelMaxOpen:
    """Tests for the max-open-tickets check in the panel view."""

    @pytest.mark.asyncio
    async def test_blocked_at_max_open(self) -> None:
        """When user has reached the max, they get a rejection message."""
        bot = _mock_bot_with_services(max_open_allowed=False)
        view = TicketPanelView(bot)
        interaction = FakeInteraction()

        await view._on_create_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done


# ---------------------------------------------------------------------------
# TicketActionView — claim button
# ---------------------------------------------------------------------------


class TestTicketClaimButton:
    """Tests for the claim button on TicketActionView."""

    @pytest.mark.asyncio
    async def test_claim_ticket_staff_only(self) -> None:
        """Non-staff user cannot claim."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123, "claimed_by": None}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 42
        user.roles = []
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        interaction.channel = thread

        await view._on_claim_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done
        bot.services.ticket.claim_ticket.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_claim_ticket_admin_allowed(self) -> None:
        """Admin can claim a ticket."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123, "claimed_by": None}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 999
        user.roles = []
        user.mention = "@admin"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = True

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.send = AsyncMock()
        interaction.channel = thread

        await view._on_claim_ticket(interaction)  # type: ignore[arg-type]
        bot.services.ticket.claim_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unclaim_ticket_toggle(self) -> None:
        """Clicking claim when already claimed by the same user unclaims."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123, "claimed_by": 999}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 999  # same as claimed_by
        user.roles = []
        user.mention = "@admin"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = True

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.send = AsyncMock()
        interaction.channel = thread

        await view._on_claim_ticket(interaction)  # type: ignore[arg-type]
        bot.services.ticket.unclaim_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claim_ticket_category_role_allowed(self) -> None:
        """A user with a category Notified Role can claim the ticket."""
        ticket = {
            "id": 1,
            "user_id": 42,
            "guild_id": 123,
            "claimed_by": None,
            "category_id": 5,
        }
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        bot.services.ticket.get_category = AsyncMock(
            return_value={"id": 5, "role_ids": [777]}
        )
        view = TicketActionView(bot)

        role = SimpleNamespace(id=777)
        user = MagicMock(spec=discord.Member)
        user.id = 999
        user.roles = [role]
        user.mention = "@helper"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.send = AsyncMock()
        interaction.channel = thread

        await view._on_claim_ticket(interaction)  # type: ignore[arg-type]
        bot.services.ticket.claim_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claim_ticket_global_staff_allowed_when_category_roles_set(
        self,
    ) -> None:
        """Global staff can still claim when category has separate notified roles."""
        ticket = {
            "id": 1,
            "user_id": 42,
            "guild_id": 123,
            "claimed_by": None,
            "category_id": 5,
        }
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[888]")
        bot.services.ticket.get_category = AsyncMock(
            return_value={"id": 5, "role_ids": [777]}
        )
        view = TicketActionView(bot)

        role = SimpleNamespace(id=888)
        user = MagicMock(spec=discord.Member)
        user.id = 999
        user.roles = [role]
        user.mention = "@global"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.send = AsyncMock()
        interaction.channel = thread

        await view._on_claim_ticket(interaction)  # type: ignore[arg-type]
        bot.services.ticket.claim_ticket.assert_awaited_once()


# ---------------------------------------------------------------------------
# TicketActionView — reopen button
# ---------------------------------------------------------------------------


class TestTicketReopenButton:
    """Tests for the reopen button."""

    @pytest.mark.asyncio
    async def test_view_has_reopen_button(self) -> None:
        """Action view includes the reopen button with the correct custom_id."""
        bot = _mock_bot_with_services()
        view = TicketActionView(bot)
        custom_ids = {c.custom_id for c in view.children}  # type: ignore[attr-defined]
        assert "ticket_action_reopen_button" in custom_ids

    @pytest.mark.asyncio
    async def test_reopen_not_in_thread(self) -> None:
        """Reopen button outside a thread sends an error."""
        bot = _mock_bot_with_services()
        view = TicketActionView(bot)
        interaction = FakeInteraction()
        interaction.channel = MagicMock(spec=discord.TextChannel)

        await view._on_reopen_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_reopen_unauthorized(self) -> None:
        """Non-creator, non-staff user cannot reopen."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 1  # not the creator
        user.roles = []
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        interaction.channel = thread

        await view._on_reopen_ticket(interaction)  # type: ignore[arg-type]
        assert interaction.response._is_done
        bot.services.ticket.reopen_ticket.assert_not_awaited()


# ---------------------------------------------------------------------------
# TicketActionView — delete button
# ---------------------------------------------------------------------------


class TestTicketDeleteButton:
    """Tests for the delete button."""

    @pytest.mark.asyncio
    async def test_delete_ticket_unauthorized(self) -> None:
        """Non-creator, non-staff user cannot delete."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 1
        user.roles = []
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.delete = AsyncMock()
        interaction.channel = thread

        await view._on_delete_ticket(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        thread.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_ticket_creator_allowed(self) -> None:
        """Ticket creator can delete the thread."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 42
        user.roles = []
        user.mention = "@creator"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        followup_send = AsyncMock()
        interaction.followup.send = followup_send
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.delete = AsyncMock()
        interaction.channel = thread

        with patch("helpers.ticket_views._log_ticket_event", new=AsyncMock()):
            await view._on_delete_ticket(interaction)  # type: ignore[arg-type]

        thread.delete.assert_awaited_once()
        bot.services.ticket.mark_thread_deleted.assert_awaited_once_with(55555)
        followup_send.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_ticket_forbidden_reports_error(self) -> None:
        """Delete reports permissions error when bot cannot delete thread."""
        ticket = {"id": 1, "user_id": 42, "guild_id": 123}
        bot = _mock_bot_with_services(ticket=ticket, staff_roles="[]")
        view = TicketActionView(bot)

        user = MagicMock(spec=discord.Member)
        user.id = 42
        user.roles = []
        user.mention = "@creator"
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False

        interaction = FakeInteraction(user=user)
        followup_send = AsyncMock()
        interaction.followup.send = followup_send
        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.delete = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "forbidden"))
        interaction.channel = thread

        await view._on_delete_ticket(interaction)  # type: ignore[arg-type]

        followup_send.assert_awaited()
        assert followup_send.await_args is not None
        args, _kwargs = followup_send.await_args
        assert "don't have permission" in args[0]


# ---------------------------------------------------------------------------
# _close_ticket
# ---------------------------------------------------------------------------


class TestCloseTicketFlow:
    """Tests for explicit thread close behavior."""

    @pytest.mark.asyncio
    async def test_close_ticket_archives_and_locks_thread_not_delete(self) -> None:
        """Closing a ticket archives + locks the thread and never deletes it."""
        bot = _mock_bot_with_services(ticket={"id": 1, "user_id": 42, "guild_id": 123})
        interaction = FakeInteraction()
        followup_send = AsyncMock()
        interaction.followup.send = followup_send

        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.mention = "#ticket-thread"
        thread.send = AsyncMock()
        thread.edit = AsyncMock()
        thread.delete = AsyncMock()

        with patch("helpers.ticket_views._generate_transcript", new=AsyncMock(return_value=None)):
            with patch("helpers.ticket_views._log_ticket_event", new=AsyncMock()):
                await _close_ticket(bot, interaction, thread, close_reason="Done")  # type: ignore[arg-type]

        thread.edit.assert_awaited_once()
        kwargs = thread.edit.await_args.kwargs
        assert kwargs.get("archived") is True
        assert kwargs.get("locked") is True
        thread.delete.assert_not_awaited()
        followup_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_ticket_reports_archive_failure(self) -> None:
        """When archive/lock fails, it is logged without additional followups."""
        bot = _mock_bot_with_services(ticket={"id": 1, "user_id": 42, "guild_id": 123})
        interaction = FakeInteraction()
        followup_send = AsyncMock()
        interaction.followup.send = followup_send

        thread = MagicMock(spec=discord.Thread)
        thread.id = 55555
        thread.mention = "#ticket-thread"
        thread.send = AsyncMock()
        thread.edit = AsyncMock(
            side_effect=discord.HTTPException(
                response=cast("Any", SimpleNamespace(status=500, reason="Server Error")),
                message="archive failed",
            )
        )

        with patch("helpers.ticket_views._generate_transcript", new=AsyncMock(return_value=None)):
            with patch("helpers.ticket_views._log_ticket_event", new=AsyncMock()):
                with patch("helpers.ticket_views.logger.exception") as log_exception:
                    await _close_ticket(bot, interaction, thread, close_reason="Done")  # type: ignore[arg-type]

        log_exception.assert_called()
        followup_send.assert_not_awaited()
