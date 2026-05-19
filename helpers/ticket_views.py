"""
Ticket Views Module

Persistent Discord UI components for the ticketing system:
- ``TicketPanelView``    — "Create Ticket" button (lives on the panel message).
- ``TicketActionView``   — "Claim" + "Close" + "Reopen" + "Delete"
                            buttons (lives inside ticket threads).

Ephemeral / modal components (NOT persistent):
- ``TicketCategorySelect``   — dropdown for choosing a category.
- ``TicketDescriptionModal`` — modal for initial ticket description.
- ``TicketCloseReasonModal`` — modal for providing a close reason.

Both persistent views use stable ``custom_id`` values so they survive bot
restarts.

AI Notes:
    Only ``TicketPanelView`` and ``TicketActionView`` need ``bot.add_view()``
    at startup. The modals and category select are created on-the-fly.

    Implementation is split across focused sub-modules:
      - ``ticket_views_helpers.py``  — shared pure functions
      - ``ticket_views_action.py``   — ``TicketActionView``
      - ``ticket_views_thread.py``   — thread creation / close coroutines
    This file owns the modals and panel views and re-exports everything for
    backward compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ui import (
    Button,
    Modal,
    Select,
    TextInput,
    View,
)

from helpers.ticket_views_action import TicketActionView
from helpers.ticket_views_helpers import (
    _build_missing_role_requirement_message,
    _format_ticket_thread_name,
    _generate_transcript,
    _get_category_role_requirements,
    _get_staff_and_check,
    _get_ticket_category_role_ids,
    _log_ticket_event,
    _normalize_category_role_id_set,
    _resolve_role_labels,
)
from helpers.ticket_views_thread import (
    _close_ticket,
    _create_ticket_thread,
    _start_dynamic_form,
)
from services.ticket_service import (
    DEFAULT_MAX_OPEN_PER_USER,
)
from utils.logging import get_logger

from helpers.bot_protocol import BotProtocol

logger = get_logger(__name__)

__all__ = [
    "TicketActionView",
    "TicketCategorySelect",
    "TicketCloseReasonModal",
    "TicketDescriptionModal",
    "TicketPanelView",
    "_build_missing_role_requirement_message",
    "_close_ticket",
    "_create_ticket_thread",
    "_format_ticket_thread_name",
    "_generate_transcript",
    "_get_category_role_requirements",
    "_get_staff_and_check",
    "_get_ticket_category_role_ids",
    "_log_ticket_event",
    "_normalize_category_role_id_set",
    "_resolve_role_labels",
    "_start_dynamic_form",
]


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------


class TicketDescriptionModal(Modal, title="Describe Your Issue"):
    """Modal shown when a user creates a ticket, collecting an initial description.

    After submission the actual thread-creation flow continues.
    """

    description_input: TextInput = TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Please describe your issue or question…",
        required=False,
        max_length=1024,
    )

    def __init__(
        self,
        bot: BotProtocol,
        category: dict[str, Any] | None,
        *,
        is_public: bool = False,
    ) -> None:
        super().__init__()
        self.bot = bot
        self._category = category
        self._is_public = is_public

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Defer and continue with thread creation."""
        await interaction.response.defer(ephemeral=True)
        description = self.description_input.value or None
        await _create_ticket_thread(
            self.bot,
            interaction,
            category=self._category,
            initial_description=description,
            is_public=self._is_public,
        )


class TicketCloseReasonModal(Modal, title="Close Ticket"):
    """Modal for providing an optional reason when closing a ticket."""

    reason_input: TextInput = TextInput(
        label="Reason for closing",
        style=discord.TextStyle.paragraph,
        placeholder="Optional — why is this ticket being closed?",
        required=False,
        max_length=1024,
    )

    def __init__(self, bot: BotProtocol, thread: discord.Thread) -> None:
        super().__init__()
        self.bot = bot
        self._thread = thread

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Defer, close the ticket, and follow up."""
        await interaction.response.defer(ephemeral=True)
        reason = self.reason_input.value or None
        await _close_ticket(self.bot, interaction, self._thread, close_reason=reason)


# ---------------------------------------------------------------------------
# Panel View — sits on the welcome message in the ticket channel
# ---------------------------------------------------------------------------


class TicketPanelView(View):
    """Persistent view with a single 'Create Ticket' button.

    Attached to the panel embed in the designated ticket channel.
    """

    def __init__(
        self,
        bot: BotProtocol,
        *,
        private_button_text: str = "Create Ticket",
        private_button_emoji: str | None = "🎫",
        enable_public_button: bool = False,
        public_button_text: str = "Create Public Ticket",
        public_button_emoji: str | None = "🌐",
        private_button_color: str | None = None,
        public_button_color: str | None = None,
        button_order: str = "private_first",
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        # Convert color hex codes to Discord button styles
        private_style = self._color_to_button_style(private_button_color, discord.ButtonStyle.primary)
        public_style = self._color_to_button_style(public_button_color, discord.ButtonStyle.secondary)

        create_btn: Button = Button(
            label=private_button_text,
            style=private_style,
            custom_id="ticket_create_button",
            emoji=private_button_emoji,
        )
        create_btn.callback = self._on_create_private_ticket  # type: ignore[method-assign]

        public_btn: Button | None = None
        if enable_public_button:
            public_btn = Button(
                label=public_button_text,
                style=public_style,
                custom_id="ticket_create_public_button",
                emoji=public_button_emoji,
            )
            public_btn.callback = self._on_create_public_ticket  # type: ignore[method-assign]

        # Add buttons in the specified order
        if button_order == "public_first" and public_btn:
            self.add_item(public_btn)
            self.add_item(create_btn)
        else:
            self.add_item(create_btn)
            if public_btn:
                self.add_item(public_btn)

    @staticmethod
    def _color_to_button_style(color: str | None, default: discord.ButtonStyle) -> discord.ButtonStyle:
        """Convert a hex color code to a Discord button style.

        Supports common color mappings:
        - Blue/Blurple → Primary (5865F2)
        - Gray → Secondary (4E5058)
        - Green → Success (3BA55D)
        - Red → Danger (ED4245)

        Returns the default style if color is None or unrecognized.
        """
        if not color:
            return default

        # Normalize hex color (remove # and convert to uppercase)
        normalized = color.strip().upper().lstrip("#")

        # Map common colors to button styles
        if normalized in ("5865F2", "5865F3", "5865F4", "0099FF", "3B88F3"):  # Blue/Blurple
            return discord.ButtonStyle.primary
        elif normalized in ("4E5058", "4F545C", "6C757D", "2C2F33"):  # Gray
            return discord.ButtonStyle.secondary
        elif normalized in ("3BA55D", "57F287", "43B581", "00C853"):  # Green
            return discord.ButtonStyle.success
        elif normalized in ("ED4245", "F04747", "D32F2F", "E74C3C"):  # Red
            return discord.ButtonStyle.danger

        return default

    async def _on_create_private_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the private ticket button press."""
        await self._on_create_ticket(interaction, is_public=False)

    async def _on_create_public_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the public ticket button press."""
        await self._on_create_ticket(interaction, is_public=True)

    async def _on_create_ticket(
        self,
        interaction: discord.Interaction,
        *,
        is_public: bool = False,
    ) -> None:
        """Handle ticket button press.

        Flow:
        1. Rate-limit check
        2. Max open tickets check
        3. Fetch categories → dropdown **or** description modal
        """
        if interaction.guild is None:
            await interaction.response.send_message(
                "Tickets can only be created in a server.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        ticket_service = self.bot.services.ticket
        config_service = self.bot.services.config

        # --- Rate-limit check ---
        allowed = await ticket_service.check_rate_limit(guild_id, interaction.user.id)
        if not allowed:
            remaining = await ticket_service.get_cooldown_remaining(
                guild_id, interaction.user.id
            )
            await interaction.response.send_message(
                f"⏳ Please wait **{remaining}** seconds before creating another ticket.",
                ephemeral=True,
            )
            return

        # --- Max open tickets check ---
        max_open_raw = await config_service.get_guild_setting(
            guild_id, "tickets.max_open_per_user", default=str(DEFAULT_MAX_OPEN_PER_USER)
        )
        try:
            max_open = int(max_open_raw)
        except (ValueError, TypeError):
            max_open = DEFAULT_MAX_OPEN_PER_USER

        can_open = await ticket_service.check_max_open_tickets(
            guild_id, interaction.user.id, max_open
        )
        if not can_open:
            await interaction.response.send_message(
                f"❌ You already have **{max_open}** open ticket(s). "
                "Please close an existing ticket before opening a new one.",
                ephemeral=True,
            )
            return

        # --- Fetch categories for this channel ---
        panel_channel_id = interaction.channel_id or 0
        categories = await ticket_service.get_categories_for_channel(
            guild_id, panel_channel_id
        )

        if not categories:
            # Fall back to all guild categories (legacy / unassigned)
            categories = await ticket_service.get_categories(guild_id)

        if not categories:
            # No categories at all — go straight to description modal
            modal = TicketDescriptionModal(
                self.bot,
                category=None,
                is_public=is_public,
            )
            await interaction.response.send_modal(modal)
            return

        # Show category dropdown
        select_view = View(timeout=60)
        select = TicketCategorySelect(self.bot, categories, is_public=is_public)
        select_view.add_item(select)
        await interaction.response.send_message(
            "Select a category for your ticket:",
            view=select_view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Category Select — ephemeral dropdown (NOT persistent)
# ---------------------------------------------------------------------------


class TicketCategorySelect(Select):
    """Dropdown for choosing a ticket category before thread creation."""

    def __init__(
        self,
        bot: BotProtocol,
        categories: list[dict[str, Any]],
        *,
        is_public: bool = False,
    ) -> None:
        self.bot = bot
        self._is_public = is_public
        self._categories = {str(c["id"]): c for c in categories}

        options = []
        for cat in categories[:25]:  # Discord max 25 options
            options.append(
                discord.SelectOption(
                    label=cat["name"],
                    description=(cat.get("description") or "")[:100],
                    value=str(cat["id"]),
                    emoji=cat.get("emoji"),
                )
            )

        super().__init__(
            placeholder="Choose a category…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """User selected a category — show dynamic form or description modal.

        If the selected category has a form configuration, start the
        dynamic modal routing flow.  Otherwise, fall back to the legacy
        ``TicketDescriptionModal``.
        """
        selected_id = self.values[0]
        category = self._categories.get(selected_id)

        if category is None:
            modal = TicketDescriptionModal(
                self.bot,
                category=None,
                is_public=self._is_public,
            )
            await interaction.response.send_modal(modal)
            return

        required_all, required_any = _get_category_role_requirements(category)
        if required_all or required_any:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Tickets can only be created in a server.", ephemeral=True
                )
                return

            member_roles = getattr(interaction.user, "roles", [])
            member_role_ids = {
                role.id
                for role in member_roles
                if getattr(role, "id", None) is not None
            }
            missing_all = required_all - member_role_ids
            missing_any = set()
            if required_any and not member_role_ids.intersection(required_any):
                missing_any = required_any

            if missing_all or missing_any:
                requirement_message = _build_missing_role_requirement_message(
                    interaction.guild,
                    missing_all,
                    missing_any,
                )
                await interaction.response.send_message(
                    f"❌ {requirement_message}",
                    ephemeral=True,
                )
                return

        # Check for dynamic form configuration
        ticket_form_service = None
        try:
            ticket_form_service = self.bot.services.ticket_form
            has_form = await ticket_form_service.has_form(category["id"])
        except (RuntimeError, AttributeError):
            # Service not available — fall back to legacy
            has_form = False

        if not has_form:
            modal = TicketDescriptionModal(
                self.bot,
                category=category,
                is_public=self._is_public,
            )
            await interaction.response.send_modal(modal)
            return

        # --- Dynamic form flow ---
        await _start_dynamic_form(
            self.bot,
            interaction,
            category,
            ticket_form_service,
            is_public=self._is_public,
        )


