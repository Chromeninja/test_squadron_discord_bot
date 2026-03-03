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
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import discord  # type: ignore[import-not-found]
from discord.ui import (  # type: ignore[import-not-found]
    Button,
    Modal,
    Select,
    TextInput,
    View,
)

from helpers.embeds import EmbedColors, create_embed
from services.ticket_service import (
    DEFAULT_MAX_OPEN_PER_USER,
    DEFAULT_REOPEN_WINDOW_HOURS,
    TicketService,
)
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers — shared across views
# ---------------------------------------------------------------------------


async def _get_staff_and_check(
    bot: MyBot,
    guild_id: int,
    member: discord.Member,
    extra_role_ids: list[int] | None = None,
) -> bool:
    """Return ``True`` if *member* is considered ticket-staff.

    Staff = has a configured global ticket-staff role, a ticket-specific
    category role, or the ``administrator`` guild permission.
    """
    config_service = bot.services.config
    staff_role_ids = await TicketService.get_staff_role_ids(config_service, guild_id)
    if extra_role_ids:
        staff_role_ids = list(set(staff_role_ids) | set(extra_role_ids))
    member_role_ids = {r.id for r in member.roles}
    if member_role_ids & set(staff_role_ids):
        return True
    return member.guild_permissions.administrator


async def _get_ticket_category_role_ids(
    ticket_service: Any,
    ticket: dict[str, Any],
) -> list[int]:
    """Return role IDs configured on the ticket's category, if any."""
    category_id = ticket.get("category_id")
    if not category_id:
        return []

    try:
        category = await ticket_service.get_category(int(category_id))
    except (TypeError, ValueError, AttributeError):
        return []

    if not isinstance(category, dict):
        return []

    role_ids_raw = category.get("role_ids")
    if not isinstance(role_ids_raw, list):
        return []

    role_ids: list[int] = []
    for role_id in role_ids_raw:
        try:
            role_ids.append(int(role_id))
        except (TypeError, ValueError):
            continue

    return role_ids


async def _log_ticket_event(
    bot: MyBot,
    guild_id: int,
    *,
    title: str,
    description: str,
    color: int,
) -> None:
    """Send a ticket event embed to the configured log channel."""
    try:
        config_service = bot.services.config
        log_channel_id = await config_service.get_guild_setting(
            guild_id, "tickets.log_channel_id"
        )
        if not log_channel_id:
            return

        channel = bot.get_channel(int(log_channel_id))
        if channel is None or not isinstance(channel, discord.TextChannel):
            return

        embed = create_embed(title=title, description=description, color=color)
        await channel.send(embed=embed)
    except Exception as e:
        logger.exception(
            "Failed to log ticket event to channel in guild %s",
            guild_id,
            exc_info=e,
        )


def _normalize_category_role_id_set(
    raw_role_ids: Any,
) -> set[int]:
    """Normalize category role requirement values into an integer ID set."""
    if not isinstance(raw_role_ids, list):
        return set()

    normalized: set[int] = set()
    for raw_role_id in raw_role_ids:
        try:
            role_id = int(raw_role_id)
        except (TypeError, ValueError):
            continue
        if role_id > 0:
            normalized.add(role_id)

    return normalized


def _get_category_role_requirements(
    category: dict[str, Any],
) -> tuple[set[int], set[int]]:
    """Return ``(required_all, required_any)`` role-ID sets for a category."""
    required_all = _normalize_category_role_id_set(
        category.get("prerequisite_role_ids_all")
    )
    required_any = _normalize_category_role_id_set(
        category.get("prerequisite_role_ids_any")
    )
    return required_all, required_any


def _resolve_role_labels(guild: discord.Guild, role_ids: set[int]) -> list[str]:
    """Resolve role IDs to display labels for user-facing requirement errors."""
    labels: list[str] = []
    for role_id in sorted(role_ids):
        role = guild.get_role(role_id)
        if role is None:
            labels.append(f"<@&{role_id}>")
            continue
        labels.append(role.mention)
    return labels


def _build_missing_role_requirement_message(
    guild: discord.Guild,
    missing_all: set[int],
    required_any: set[int],
) -> str:
    """Build the popup message shown when category role requirements fail."""
    all_labels = _resolve_role_labels(guild, missing_all)
    any_labels = _resolve_role_labels(guild, required_any)

    if all_labels and not any_labels:
        if len(all_labels) == 1:
            return f"You need {all_labels[0]} role to create a ticket here."
        return (
            "You need all of these roles to create a ticket here: "
            f"{', '.join(all_labels)}."
        )

    if any_labels and not all_labels:
        if len(any_labels) == 1:
            return f"You need {any_labels[0]} role to create a ticket here."
        return (
            "You need at least one of these roles to create a ticket here: "
            f"{', '.join(any_labels)}."
        )

    return (
        "You need all of these roles "
        f"({', '.join(all_labels)}) and at least one of these roles "
        f"({', '.join(any_labels)}) to create a ticket here."
    )


def _format_ticket_thread_name(
    ticket_id: int,
    category_label: str,
    user_display_name: str,
) -> str:
    """Format a ticket thread name using the standard naming convention."""
    safe_category = " ".join(str(category_label).split())
    safe_user = " ".join(str(user_display_name).split())
    return f"T:{ticket_id:02d} - {safe_category} - {safe_user}"[:100]


async def _generate_transcript(thread: discord.Thread) -> discord.File:
    """Generate a plain-text transcript of a ticket thread.

    Returns a ``discord.File`` that can be attached to a message.
    """
    lines: list[str] = []
    lines.append(f"=== Transcript for #{thread.name} ===")
    lines.append(f"Thread ID: {thread.id}")
    lines.append(f"Created: {thread.created_at or 'unknown'}")
    lines.append("=" * 50)
    lines.append("")

    async for message in thread.history(limit=500, oldest_first=True):
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{message.author} ({message.author.id})"
        content = message.content or ""

        lines.append(f"[{timestamp}] {author}")
        if content:
            lines.append(content)
        for attachment in message.attachments:
            lines.append(f"  [Attachment: {attachment.filename} — {attachment.url}]")
        for embed in message.embeds:
            title = embed.title or "(no title)"
            desc = embed.description or ""
            lines.append(f"  [Embed: {title}] {desc[:200]}")
        lines.append("")

    transcript_text = "\n".join(lines)
    buffer = io.BytesIO(transcript_text.encode("utf-8"))
    filename = f"transcript-{thread.name}-{thread.id}.txt"
    return discord.File(buffer, filename=filename)


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------


class TicketDescriptionModal(Modal, title="Describe Your Issue"):
    """Modal shown when a user creates a ticket, collecting an initial description.

    After submission the actual thread-creation flow continues.
    """

    description_input = TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Please describe your issue or question…",
        required=False,
        max_length=1024,
    )

    def __init__(
        self,
        bot: MyBot,
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

    reason_input = TextInput(
        label="Reason for closing",
        style=discord.TextStyle.paragraph,
        placeholder="Optional — why is this ticket being closed?",
        required=False,
        max_length=1024,
    )

    def __init__(self, bot: MyBot, thread: discord.Thread) -> None:
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
        bot: MyBot,
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

        create_btn = Button(
            label=private_button_text,
            style=private_style,
            custom_id="ticket_create_button",
            emoji=private_button_emoji,
        )
        create_btn.callback = self._on_create_private_ticket

        public_btn = None
        if enable_public_button:
            public_btn = Button(
                label=public_button_text,
                style=public_style,
                custom_id="ticket_create_public_button",
                emoji=public_button_emoji,
            )
            public_btn.callback = self._on_create_public_ticket

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
        bot: MyBot,
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


# ---------------------------------------------------------------------------
# Action View — sits inside each ticket thread (Claim/Close/Reopen/Delete)
# ---------------------------------------------------------------------------


class TicketActionView(View):
    """Persistent view with ticket action buttons inside a ticket thread."""

    def __init__(
        self,
        bot: MyBot,
        *,
        ticket_is_closed: bool = False,
        reopen_enabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        claim_btn = Button(
            label="Claim",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_action_claim_button",
            emoji="🙋",
            disabled=ticket_is_closed,
        )
        claim_btn.callback = self._on_claim_ticket
        self.add_item(claim_btn)

        close_btn = Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_action_close_button",
            emoji="🔒",
            disabled=ticket_is_closed,
        )
        close_btn.callback = self._on_close_ticket
        self.add_item(close_btn)

        reopen_btn = Button(
            label="Reopen Ticket",
            style=discord.ButtonStyle.success,
            custom_id="ticket_action_reopen_button",
            emoji="🔓",
            disabled=(not ticket_is_closed) or (not reopen_enabled),
        )
        reopen_btn.callback = self._on_reopen_ticket
        self.add_item(reopen_btn)

        delete_btn = Button(
            label="Delete Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_action_delete_button",
            emoji="🗑️",
        )
        delete_btn.callback = self._on_delete_ticket
        self.add_item(delete_btn)

    # -- Claim --

    async def _on_claim_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the 'Claim' button — assign a staff member to the ticket."""
        if interaction.guild is None or not isinstance(
            interaction.channel, discord.Thread
        ):
            await interaction.response.send_message(
                "This button only works inside a ticket thread.", ephemeral=True
            )
            return

        thread = interaction.channel
        guild_id = interaction.guild.id
        ticket_service = self.bot.services.ticket

        ticket = await ticket_service.get_ticket_by_thread(thread.id)
        if ticket is None:
            await interaction.response.send_message(
                "Could not find a ticket record for this thread.", ephemeral=True
            )
            return

        # Only staff can claim
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Could not verify your roles.", ephemeral=True
            )
            return

        category_role_ids = await _get_ticket_category_role_ids(ticket_service, ticket)
        is_staff = await _get_staff_and_check(
            self.bot,
            guild_id,
            interaction.user,
            extra_role_ids=category_role_ids,
        )
        if not is_staff:
            await interaction.response.send_message(
                "Only staff members can claim tickets.", ephemeral=True
            )
            return

        # Toggle claim: if already claimed by this user, unclaim
        if ticket.get("claimed_by") == interaction.user.id:
            await ticket_service.unclaim_ticket(thread.id)
            await interaction.response.send_message(
                "✅ You have released your claim on this ticket.", ephemeral=True
            )
            unclaim_embed = create_embed(
                title="🙋 Claim Released",
                description=f"{interaction.user.mention} released their claim on this ticket.",
                color=EmbedColors.WARNING,
            )
            await thread.send(embed=unclaim_embed)
            return

        # If already claimed by someone else, notify
        if ticket.get("claimed_by"):
            await interaction.response.send_message(
                f"This ticket is already claimed by <@{ticket['claimed_by']}>. "
                "They must release it first.",
                ephemeral=True,
            )
            return

        # Claim it
        claimed = await ticket_service.claim_ticket(thread.id, interaction.user.id)
        if not claimed:
            await interaction.response.send_message(
                "Failed to claim this ticket.", ephemeral=True
            )
            return

        claim_embed = create_embed(
            title="🙋 Ticket Claimed",
            description=f"{interaction.user.mention} is now handling this ticket.",
            color=EmbedColors.SUCCESS,
        )
        await interaction.response.send_message(embed=claim_embed)

        await _log_ticket_event(
            self.bot,
            guild_id,
            title="🙋 Ticket Claimed",
            description=(
                f"**Ticket:** {thread.mention}\n"
                f"**Claimed by:** {interaction.user.mention}"
            ),
            color=EmbedColors.INFO,
        )

    # -- Close --

    async def _on_close_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the 'Close Ticket' button — show close-reason modal."""
        if interaction.guild is None or not isinstance(
            interaction.channel, discord.Thread
        ):
            await interaction.response.send_message(
                "This button only works inside a ticket thread.", ephemeral=True
            )
            return

        thread = interaction.channel
        guild_id = interaction.guild.id
        ticket_service = self.bot.services.ticket

        # Look up the ticket
        ticket = await ticket_service.get_ticket_by_thread(thread.id)
        if ticket is None:
            await interaction.response.send_message(
                "Could not find a ticket record for this thread.", ephemeral=True
            )
            return

        # --- Permission check ---
        user_id = interaction.user.id
        is_creator = user_id == ticket["user_id"]
        is_staff = False

        if isinstance(interaction.user, discord.Member):
            category_role_ids = await _get_ticket_category_role_ids(ticket_service, ticket)
            is_staff = await _get_staff_and_check(
                self.bot,
                guild_id,
                interaction.user,
                extra_role_ids=category_role_ids,
            )

        if not is_creator and not is_staff:
            await interaction.response.send_message(
                "You do not have permission to close this ticket.", ephemeral=True
            )
            return

        # Show the close-reason modal
        modal = TicketCloseReasonModal(self.bot, thread)
        await interaction.response.send_modal(modal)

    async def _on_reopen_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the 'Reopen' button press."""
        if interaction.guild is None or not isinstance(
            interaction.channel, discord.Thread
        ):
            await interaction.response.send_message(
                "This button only works inside a ticket thread.", ephemeral=True
            )
            return

        thread = interaction.channel
        guild_id = interaction.guild.id
        ticket_service = self.bot.services.ticket
        config_service = self.bot.services.config

        ticket = await ticket_service.get_ticket_by_thread(thread.id)
        if ticket is None:
            await interaction.response.send_message(
                "Could not find a ticket record for this thread.", ephemeral=True
            )
            return

        # Only the creator or staff can reopen
        user_id = interaction.user.id
        is_creator = user_id == ticket["user_id"]
        is_staff = False
        if isinstance(interaction.user, discord.Member):
            category_role_ids = await _get_ticket_category_role_ids(ticket_service, ticket)
            is_staff = await _get_staff_and_check(
                self.bot,
                guild_id,
                interaction.user,
                extra_role_ids=category_role_ids,
            )

        if not is_creator and not is_staff:
            await interaction.response.send_message(
                "You do not have permission to reopen this ticket.", ephemeral=True
            )
            return

        # Check reopen window
        reopen_window_raw = await config_service.get_guild_setting(
            guild_id, "tickets.reopen_window_hours", default=str(DEFAULT_REOPEN_WINDOW_HOURS)
        )
        try:
            reopen_window = int(reopen_window_raw)
        except (ValueError, TypeError):
            reopen_window = DEFAULT_REOPEN_WINDOW_HOURS

        can_reopen = await ticket_service.can_reopen(thread.id, reopen_window)
        if not can_reopen:
            await interaction.response.send_message(
                f"⏳ The reopen window ({reopen_window}h) has passed. "
                "Please create a new ticket instead.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        reopened = await ticket_service.reopen_ticket(thread.id, user_id)
        if not reopened:
            await interaction.followup.send(
                "This ticket is not closed or could not be reopened.", ephemeral=True
            )
            return

        # Unarchive / unlock the thread
        try:
            await thread.edit(archived=False, locked=False)
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to unarchive thread %s in guild %s",
                thread.id,
                guild_id,
            )

        reopen_embed = create_embed(
            title="🔓 Ticket Reopened",
            description=f"This ticket has been reopened by {interaction.user.mention}.",
            color=EmbedColors.SUCCESS,
        )
        # Send the control view again so staff can close/claim
        action_view = TicketActionView(self.bot)
        await thread.send(embed=reopen_embed, view=action_view)

        await _log_ticket_event(
            self.bot,
            guild_id,
            title="🔓 Ticket Reopened",
            description=(
                f"**Ticket:** {thread.mention}\n"
                f"**Reopened by:** {interaction.user.mention}"
            ),
            color=EmbedColors.SUCCESS,
        )

        await interaction.followup.send("Ticket reopened.", ephemeral=True)

    async def _on_delete_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the 'Delete Ticket' button — delete the Discord thread."""
        if interaction.guild is None or not isinstance(
            interaction.channel, discord.Thread
        ):
            await interaction.response.send_message(
                "This button only works inside a ticket thread.", ephemeral=True
            )
            return

        thread = interaction.channel
        guild_id = interaction.guild.id
        ticket_service = self.bot.services.ticket

        ticket = await ticket_service.get_ticket_by_thread(thread.id)
        if ticket is None:
            await interaction.response.send_message(
                "Could not find a ticket record for this thread.", ephemeral=True
            )
            return

        # Only the creator or staff can delete
        user_id = interaction.user.id
        is_creator = user_id == ticket["user_id"]
        is_staff = False
        if isinstance(interaction.user, discord.Member):
            category_role_ids = await _get_ticket_category_role_ids(ticket_service, ticket)
            is_staff = await _get_staff_and_check(
                self.bot,
                guild_id,
                interaction.user,
                extra_role_ids=category_role_ids,
            )

        if not is_creator and not is_staff:
            await interaction.response.send_message(
                "You do not have permission to delete this ticket.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await thread.delete(
                reason=(
                    f"Ticket deleted by {interaction.user} "
                    f"({interaction.user.id})"
                )
            )
        except discord.Forbidden as e:
            logger.exception(
                "Failed to delete thread %s in guild %s due to permissions",
                thread.id,
                guild_id,
                exc_info=e,
            )
            await interaction.followup.send(
                "I don't have permission to delete this thread.", ephemeral=True
            )
            return
        except discord.HTTPException as e:
            logger.exception(
                "Discord API error while deleting thread %s in guild %s",
                thread.id,
                guild_id,
                exc_info=e,
            )
            await interaction.followup.send(
                "Failed to delete this thread due to a Discord API error.",
                ephemeral=True,
            )
            return

        # Mark the ticket's thread as deleted in the DB for analytics
        await ticket_service.mark_thread_deleted(thread.id)

        await _log_ticket_event(
            self.bot,
            guild_id,
            title="🗑️ Ticket Deleted",
            description=(
                f"**Thread:** `{thread.id}`\n"
                f"**Deleted by:** {interaction.user.mention}"
            ),
            color=EmbedColors.WARNING,
        )

        await interaction.followup.send("Ticket thread deleted.", ephemeral=True)


# ---------------------------------------------------------------------------
# Thread creation
# ---------------------------------------------------------------------------


async def _start_dynamic_form(
    bot: MyBot,
    interaction: discord.Interaction,
    category: dict[str, Any],
    ticket_form_service: Any,
    *,
    is_public: bool = False,
) -> None:
    """Begin a dynamic modal form flow for the selected category.

    Creates a route session, loads the first step's questions, builds
    a ``DynamicTicketModal``, and presents it to the user.

    AI Notes:
        Imported lazily to avoid circular imports.  The form views module
        imports ``_create_ticket_thread`` from this module.
    """
    from helpers.ticket_form_views import present_step_ui

    guild_id = interaction.guild.id if interaction.guild else 0
    user_id = interaction.user.id

    # Create fresh session
    ctx = await ticket_form_service.create_session(
        guild_id, user_id, category["id"],
        interaction_token=interaction.token,
        is_public=is_public,
    )
    ctx.category = category

    # Load form config + first step
    form_config = await ticket_form_service.get_form_config(category["id"])
    if not form_config or not form_config.get("steps"):
        # Shouldn't happen (has_form was True), but handle gracefully
        modal = TicketDescriptionModal(bot, category=category, is_public=is_public)
        await interaction.response.send_modal(modal)
        return

    steps = form_config["steps"]
    first_step = steps[0]
    questions = first_step.get("questions", [])

    if not questions:
        modal_fallback = TicketDescriptionModal(
            bot,
            category=category,
            is_public=is_public,
        )
        await interaction.response.send_modal(modal_fallback)
        return

    await present_step_ui(
        bot,
        interaction,
        category,
        first_step,
        questions,
        ctx,
        total_steps=len(steps),
    )


async def _create_ticket_thread(
    bot: MyBot,
    interaction: discord.Interaction,
    *,
    category: dict[str, Any] | None,
    initial_description: str | None = None,
    form_responses: dict[str, dict[str, Any]] | None = None,
    is_public: bool = False,
) -> int | None:
    """Create a thread for a new ticket.

    Called after the user fills in the description modal or completes
    the dynamic form route.

    Args:
        form_responses: Optional dict of collected form answers from a
            dynamic route flow.  When present, the answers are displayed
            as separate fields in the welcome embed.

    Returns:
        The new ticket's database row ID, or ``None`` on failure.

    AI Notes:
        Thread creation requires the channel to be a ``TextChannel``.
        The thread is renamed to use the ticket number once the DB record
        is created.
    """
    if interaction.guild is None or interaction.channel is None:
        await interaction.followup.send(
            "Ticket creation failed — missing guild/channel context.",
            ephemeral=True,
        )
        return None

    guild_id = interaction.guild.id
    user = interaction.user
    ticket_service = bot.services.ticket
    config_service = bot.services.config

    # Determine the originating text channel
    channel = interaction.channel
    # If interaction occurred inside a thread (from category select),
    # use the parent channel for thread creation.
    if isinstance(channel, discord.Thread):
        channel = channel.parent  # type: ignore[assignment]
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send(
            "Tickets can only be created in text channels.", ephemeral=True
        )
        return None

    cat_label = category["name"] if category else "ticket"
    thread_name = f"{cat_label}-{user.display_name}"[:100]

    try:
        thread = await channel.create_thread(
            name=thread_name,
            type=(
                discord.ChannelType.public_thread
                if is_public
                else discord.ChannelType.private_thread
            ),
            auto_archive_duration=10080,  # 7 days
            reason=f"Ticket created by {user} (category: {cat_label})",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "I don't have permission to create threads in this channel.",
            ephemeral=True,
        )
        return None
    except discord.HTTPException as exc:
        logger.exception(
            "Failed to create ticket thread in guild %s", guild_id, exc_info=exc
        )
        await interaction.followup.send(
            "Something went wrong creating your ticket. Please try again later.",
            ephemeral=True,
        )
        return None

    # Add the ticket creator to the thread
    try:
        await thread.add_user(user)
    except discord.Forbidden:
        logger.debug(
            "No permission to add user %s to thread %s", user.id, thread.id
        )
    except discord.HTTPException as exc:
        logger.warning(
            "Could not add user %s to thread %s: %s",
            user.id,
            thread.id,
            exc,
        )

    # Record in DB
    category_id = category["id"] if category else None
    ticket_id = await ticket_service.create_ticket(
        guild_id=guild_id,
        channel_id=channel.id,
        thread_id=thread.id,
        user_id=user.id,
        category_id=category_id,
        initial_description=initial_description,
    )

    # Rename thread using standard ticket naming format
    if ticket_id is not None:
        formatted_name = _format_ticket_thread_name(
            ticket_id,
            cat_label,
            user.display_name,
        )
        try:
            await thread.edit(name=formatted_name)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Could not rename thread %s to %s in guild %s",
                thread.id,
                formatted_name,
                guild_id,
            )

    # --- Welcome message ---
    if category and category.get("welcome_message"):
        welcome_text = category["welcome_message"]
    else:
        welcome_text = await config_service.get_guild_setting(
            guild_id,
            "tickets.default_welcome_message",
            default=(
                "Welcome to your support ticket!\n\n"
                "Please describe your issue and a staff member will be with you shortly.\n"
                "Click **Close Ticket** when your issue is resolved."
            ),
        )

    welcome_embed = create_embed(
        title="🎫 New Ticket",
        description=welcome_text,
        color=EmbedColors.INFO,
    )
    if category:
        welcome_embed.add_field(name="Category", value=category["name"], inline=True)
    welcome_embed.add_field(name="Created by", value=user.mention, inline=True)
    if ticket_id:
        welcome_embed.set_footer(text=f"Ticket #{ticket_id}")

    # Send user's initial description if provided
    if initial_description and not form_responses:
        welcome_embed.add_field(
            name="Description", value=initial_description[:1024], inline=False
        )

    # Display structured form responses when available
    if form_responses:
        for _qid, data in form_responses.items():
            label = data.get("label", _qid)
            answer = data.get("answer", "")
            if answer:
                welcome_embed.add_field(
                    name=label[:256], value=answer[:1024], inline=False
                )

    control_view = TicketActionView(bot)
    await thread.send(embed=welcome_embed, view=control_view)

    # --- Add staff roles to the thread ---
    if category and category.get("role_ids"):
        role_ids: list[int] = category["role_ids"]
    else:
        role_ids = await TicketService.get_staff_role_ids(config_service, guild_id)

    # Mention staff roles in the thread so they get notifications
    if role_ids and interaction.guild:
        mentions = []
        for rid in role_ids:
            role = interaction.guild.get_role(int(rid))
            if role:
                mentions.append(role.mention)
        if mentions:
            await thread.send(" ".join(mentions))

    # --- Log to log channel ---
    log_desc = (
        f"**Ticket:** {thread.mention}\n"
        f"**Creator:** {user.mention}\n"
        f"**Category:** {cat_label}"
    )
    if initial_description:
        log_desc += f"\n**Description:** {initial_description[:200]}"

    await _log_ticket_event(
        bot,
        guild_id,
        title="🎫 Ticket Opened",
        description=log_desc,
        color=EmbedColors.INFO,
    )

    await interaction.followup.send(
        f"Your ticket has been created: {thread.mention}", ephemeral=True
    )

    return ticket_id


# ---------------------------------------------------------------------------
# Close ticket flow
# ---------------------------------------------------------------------------


async def _close_ticket(
    bot: MyBot,
    interaction: discord.Interaction,
    thread: discord.Thread,
    *,
    close_reason: str | None = None,
) -> None:
    """Close a ticket thread: update DB, send transcript, archive.

    Called from the ``TicketCloseReasonModal`` after the user submits.
    """
    if interaction.guild is None:
        await interaction.followup.send("Missing guild context.", ephemeral=True)
        return

    guild_id = interaction.guild.id
    user_id = interaction.user.id
    ticket_service = bot.services.ticket
    config_service = bot.services.config

    # Close ticket in DB
    closed = await ticket_service.close_ticket_by_thread(
        thread.id, user_id, close_reason=close_reason
    )
    if not closed:
        await interaction.followup.send(
            "This ticket is already closed.", ephemeral=True
        )
        return

    # --- Generate transcript ---
    try:
        transcript_file = await _generate_transcript(thread)
    except Exception as e:
        logger.exception(
            "Failed to generate transcript for thread %s", thread.id, exc_info=e
        )
        transcript_file = None

    # --- Close message ---
    close_msg = await config_service.get_guild_setting(
        guild_id,
        "tickets.close_message",
        default="This ticket has been closed.",
    )
    close_desc = f"{close_msg}\n\nClosed by {interaction.user.mention}"
    if close_reason:
        close_desc += f"\n**Reason:** {close_reason}"

    close_embed = create_embed(
        title="🔒 Ticket Closed",
        description=close_desc,
        color=EmbedColors.ADMIN,
    )

    # Send close message + action view + transcript
    action_view = TicketActionView(bot, ticket_is_closed=True, reopen_enabled=True)
    if transcript_file:
        await thread.send(embed=close_embed, view=action_view, file=transcript_file)
    else:
        await thread.send(embed=close_embed, view=action_view)

    # Close thread (archive + lock) — never delete
    try:
        await thread.edit(
            archived=True,
            locked=True,
            reason=f"Ticket closed by {interaction.user} ({interaction.user.id})",
        )
    except discord.Forbidden as e:
        logger.exception(
            "Failed to archive/lock thread %s in guild %s due to permissions",
            thread.id,
            guild_id,
            exc_info=e,
        )
    except discord.HTTPException as e:
        logger.exception(
            "Discord API error while archiving/locking thread %s in guild %s",
            thread.id,
            guild_id,
            exc_info=e,
        )

    # --- Log to log channel ---
    ticket = await ticket_service.get_ticket_by_thread(thread.id)
    creator_mention = f"<@{ticket['user_id']}>" if ticket else "unknown"

    log_desc = (
        f"**Ticket:** {thread.mention}\n"
        f"**Closed by:** {interaction.user.mention}\n"
        f"**Creator:** {creator_mention}"
    )
    if close_reason:
        log_desc += f"\n**Reason:** {close_reason}"

    await _log_ticket_event(
        bot,
        guild_id,
        title="🔒 Ticket Closed",
        description=log_desc,
        color=EmbedColors.ADMIN,
    )
