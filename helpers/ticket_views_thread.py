"""
Ticket Views — Thread Creation and Closure

Stand-alone coroutines that handle the ticket lifecycle:

- ``_start_dynamic_form``   — route into a multi-step modal flow.
- ``_create_ticket_thread`` — create a Discord thread and DB record.
- ``_close_ticket``         — close, archive, and log a ticket thread.

AI Notes:
    ``TicketDescriptionModal`` is imported lazily inside
    ``_start_dynamic_form`` to avoid a circular import with
    ``helpers.ticket_views``, which owns that modal class.

    ``TicketActionView`` is imported lazily inside
    ``_create_ticket_thread`` and ``_close_ticket`` for the same reason
    (it lives in ``helpers.ticket_views_action``).
"""

from __future__ import annotations

from typing import Any

import discord

from helpers.embeds import EmbedColors, create_embed
from helpers.ticket_views_helpers import (
    _format_ticket_thread_name,
    _generate_transcript,
    _log_ticket_event,
)
from services.ticket_service import TicketService
from utils.logging import get_logger

from helpers.bot_protocol import BotProtocol

logger = get_logger(__name__)


async def _start_dynamic_form(
    bot: BotProtocol,
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
    from helpers.ticket_views import TicketDescriptionModal

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
    bot: BotProtocol,
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
    from helpers.ticket_views_action import TicketActionView

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


async def _close_ticket(
    bot: BotProtocol,
    interaction: discord.Interaction,
    thread: discord.Thread,
    *,
    close_reason: str | None = None,
) -> None:
    """Close a ticket thread: update DB, send transcript, archive.

    Called from the ``TicketCloseReasonModal`` after the user submits.
    """
    from helpers.ticket_views_action import TicketActionView

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
