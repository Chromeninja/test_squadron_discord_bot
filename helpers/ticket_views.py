"""
Ticket Views Module

Persistent Discord UI components for the ticketing system:
- ``TicketPanelView``   — "Create Ticket" button (lives on the panel message).
- ``TicketControlView`` — "Close Ticket" button (lives inside each ticket thread).

Both use stable ``custom_id`` values so they survive bot restarts.

AI Notes:
    The ``TicketCategorySelect`` is ephemeral — it is created on-the-fly
    when the user clicks "Create Ticket" and is not registered as a
    persistent view.  Only ``TicketPanelView`` and ``TicketControlView``
    need ``bot.add_view()`` at startup.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import discord  # type: ignore[import-not-found]
from discord.ui import Button, Select, View  # type: ignore[import-not-found]

from helpers.embeds import EmbedColors, create_embed
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Panel View — sits on the welcome message in the ticket channel
# ---------------------------------------------------------------------------


class TicketPanelView(View):
    """Persistent view with a single 'Create Ticket' button.

    Attached to the panel embed in the designated ticket channel.
    """

    def __init__(self, bot: MyBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        create_btn = Button(
            label="Create Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_create_button",
            emoji="🎫",
        )
        create_btn.callback = self._on_create_ticket
        self.add_item(create_btn)

    async def _on_create_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the 'Create Ticket' button press.

        Fetches categories for the guild and shows a dropdown if categories
        exist, otherwise creates a ticket directly (uncategorised).
        """
        if interaction.guild is None:
            await interaction.response.send_message(
                "Tickets can only be created in a server.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        ticket_service = self.bot.services.ticket

        # --- Rate limit check ---
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

        # --- Fetch categories ---
        categories = await ticket_service.get_categories(guild_id)

        if not categories:
            # No categories configured — create ticket directly
            await interaction.response.defer(ephemeral=True)
            await _create_ticket_thread(self.bot, interaction, category=None)
            return

        # Show category dropdown
        select_view = View(timeout=60)
        select = TicketCategorySelect(self.bot, categories)
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

    def __init__(self, bot: MyBot, categories: list[dict[str, Any]]) -> None:
        self.bot = bot
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
        """User selected a category — create the ticket thread."""
        selected_id = self.values[0]
        category = self._categories.get(selected_id)

        await interaction.response.defer(ephemeral=True)
        await _create_ticket_thread(self.bot, interaction, category=category)


# ---------------------------------------------------------------------------
# Control View — sits inside each ticket thread
# ---------------------------------------------------------------------------


class TicketControlView(View):
    """Persistent view with a 'Close Ticket' button inside a ticket thread."""

    def __init__(self, bot: MyBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        close_btn = Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_close_button",
            emoji="🔒",
        )
        close_btn.callback = self._on_close_ticket
        self.add_item(close_btn)

    async def _on_close_ticket(self, interaction: discord.Interaction) -> None:
        """Handle the 'Close Ticket' button press."""
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
            staff_roles_raw = await config_service.get_guild_setting(
                guild_id, "tickets.staff_roles", default="[]"
            )
            try:
                staff_role_ids: list[int] = (
                    json.loads(staff_roles_raw)
                    if isinstance(staff_roles_raw, str)
                    else (staff_roles_raw or [])
                )
            except (json.JSONDecodeError, TypeError):
                staff_role_ids = []

            member_role_ids = {r.id for r in interaction.user.roles}
            if member_role_ids & set(staff_role_ids):
                is_staff = True

            # Guild admins / bot admins can always close
            if interaction.user.guild_permissions.administrator:
                is_staff = True

        if not is_creator and not is_staff:
            await interaction.response.send_message(
                "You do not have permission to close this ticket.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Close ticket in DB
        closed = await ticket_service.close_ticket_by_thread(thread.id, user_id)
        if not closed:
            await interaction.followup.send(
                "This ticket is already closed.", ephemeral=True
            )
            return

        # --- Close message ---
        close_msg = await config_service.get_guild_setting(
            guild_id,
            "tickets.close_message",
            default="This ticket has been closed.",
        )
        close_embed = create_embed(
            title="🔒 Ticket Closed",
            description=f"{close_msg}\n\nClosed by {interaction.user.mention}",
            color=EmbedColors.ADMIN,
        )
        await thread.send(embed=close_embed)

        # Archive + lock the thread
        try:
            await thread.edit(archived=True, locked=True)
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to archive/lock thread %s in guild %s",
                thread.id,
                guild_id,
            )

        # --- Log to log channel ---
        await _log_ticket_event(
            self.bot,
            guild_id,
            title="🔒 Ticket Closed",
            description=(
                f"**Ticket:** {thread.mention}\n"
                f"**Closed by:** {interaction.user.mention}\n"
                f"**Creator:** <@{ticket['user_id']}>"
            ),
            color=EmbedColors.ADMIN,
        )

        await interaction.followup.send("Ticket closed.", ephemeral=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_ticket_thread(
    bot: MyBot,
    interaction: discord.Interaction,
    *,
    category: dict[str, Any] | None,
) -> None:
    """Create a private thread for a new ticket.

    Called after the user clicks the panel button (possibly after selecting
    a category).

    AI Notes:
        Private threads require the channel to be a ``TextChannel``.
        The thread is renamed to use the ticket number once the DB record
        is created.
    """
    if interaction.guild is None or interaction.channel is None:
        await interaction.followup.send(
            "Ticket creation failed — missing guild/channel context.",
            ephemeral=True,
        )
        return

    guild_id = interaction.guild.id
    user = interaction.user
    ticket_service = bot.services.ticket
    config_service = bot.services.config

    # Temporary thread name (renamed to ticket number after DB insert)
    cat_label = category["name"] if category else "ticket"
    thread_name = f"{cat_label}-{user.display_name}"[:100]

    # Create private thread
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send(
            "Tickets can only be created in text channels.", ephemeral=True
        )
        return

    try:
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=10080,  # 7 days
            reason=f"Ticket created by {user} (category: {cat_label})",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "I don't have permission to create private threads in this channel.",
            ephemeral=True,
        )
        return
    except discord.HTTPException as exc:
        logger.exception(
            "Failed to create ticket thread in guild %s", guild_id, exc_info=exc
        )
        await interaction.followup.send(
            "Something went wrong creating your ticket. Please try again later.",
            ephemeral=True,
        )
        return

    # Add the ticket creator to the thread
    try:
        await thread.add_user(user)
    except discord.HTTPException:
        pass  # non-critical

    # Record in DB
    category_id = category["id"] if category else None
    ticket_id = await ticket_service.create_ticket(
        guild_id=guild_id,
        channel_id=channel.id,
        thread_id=thread.id,
        user_id=user.id,
        category_id=category_id,
    )

    # Rename thread to ticket number for consistent UX
    if ticket_id is not None:
        try:
            await thread.edit(name=f"ticket-{ticket_id}")
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Could not rename thread %s to ticket-%s in guild %s",
                thread.id,
                ticket_id,
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

    control_view = TicketControlView(bot)
    await thread.send(embed=welcome_embed, view=control_view)

    # --- Add staff roles to the thread ---
    if category and category.get("role_ids"):
        role_ids = category["role_ids"]
    else:
        staff_raw = await config_service.get_guild_setting(
            guild_id, "tickets.staff_roles", default="[]"
        )
        try:
            role_ids = (
                json.loads(staff_raw)
                if isinstance(staff_raw, str)
                else (staff_raw or [])
            )
        except (json.JSONDecodeError, TypeError):
            role_ids = []

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
    await _log_ticket_event(
        bot,
        guild_id,
        title="🎫 Ticket Opened",
        description=(
            f"**Ticket:** {thread.mention}\n"
            f"**Creator:** {user.mention}\n"
            f"**Category:** {cat_label}"
        ),
        color=EmbedColors.INFO,
    )

    await interaction.followup.send(
        f"Your ticket has been created: {thread.mention}", ephemeral=True
    )


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
        if channel is None:
            return

        if not isinstance(channel, discord.TextChannel):
            return

        embed = create_embed(title=title, description=description, color=color)
        await channel.send(embed=embed)
    except Exception as e:
        logger.exception(
            "Failed to log ticket event to channel in guild %s",
            guild_id,
            exc_info=e,
        )
