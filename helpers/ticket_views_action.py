"""
Ticket Views — Action View

``TicketActionView`` — the persistent view with Claim / Close / Reopen /
Delete buttons that lives inside every ticket thread.

AI Notes:
    ``TicketCloseReasonModal`` is imported lazily inside
    ``_on_close_ticket`` to avoid a circular import with
    ``helpers.ticket_views``, which defines that modal and imports this
    module for re-export.

    ``_close_ticket`` is imported lazily inside ``_on_close_ticket`` for
    the same reason (it lives in ``helpers.ticket_views_thread``).
"""

from __future__ import annotations

import discord
from discord.ui import Button, View

from helpers.bot_protocol import BotProtocol
from helpers.embeds import EmbedColors, create_embed
from helpers.ticket_views_helpers import (
    _get_staff_and_check,
    _get_ticket_category_role_ids,
    _log_ticket_event,
)
from utils.logging import get_logger

logger = get_logger(__name__)


class TicketActionView(View):
    """Persistent view with ticket action buttons inside a ticket thread."""

    def __init__(
        self,
        bot: BotProtocol,
        *,
        ticket_is_closed: bool = False,
        reopen_enabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        claim_btn: Button = Button(
            label="Claim",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_action_claim_button",
            emoji="🙋",
            disabled=ticket_is_closed,
        )
        claim_btn.callback = self._on_claim_ticket  # type: ignore[method-assign]
        self.add_item(claim_btn)

        close_btn: Button = Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_action_close_button",
            emoji="🔒",
            disabled=ticket_is_closed,
        )
        close_btn.callback = self._on_close_ticket  # type: ignore[method-assign]
        self.add_item(close_btn)

        reopen_btn: Button = Button(
            label="Reopen Ticket",
            style=discord.ButtonStyle.success,
            custom_id="ticket_action_reopen_button",
            emoji="🔓",
            disabled=(not ticket_is_closed) or (not reopen_enabled),
        )
        reopen_btn.callback = self._on_reopen_ticket  # type: ignore[method-assign]
        self.add_item(reopen_btn)

        delete_btn: Button = Button(
            label="Delete Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_action_delete_button",
            emoji="🗑️",
        )
        delete_btn.callback = self._on_delete_ticket  # type: ignore[method-assign]
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

        # Lazy import to avoid circular import with helpers.ticket_views
        from helpers.ticket_views import TicketCloseReasonModal

        modal = TicketCloseReasonModal(self.bot, thread)
        await interaction.response.send_modal(modal)

    # -- Reopen --

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
        from services.ticket_service import (
            DEFAULT_REOPEN_WINDOW_HOURS,
        )

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

    # -- Delete --

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
            color=EmbedColors.ADMIN,
        )

        await interaction.followup.send("Ticket thread deleted.", ephemeral=True)
