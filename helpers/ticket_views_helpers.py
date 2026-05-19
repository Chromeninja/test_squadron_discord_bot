"""
Ticket Views — Shared Helper Functions

Pure utility functions used by all ticket view classes.  No discord.py
UI classes live here — only plain functions shared across the ticket
view modules.

AI Notes:
    This module is intentionally free of discord.py UI class imports so it
    can be imported by ticket_views_thread.py and ticket_views_action.py
    without triggering circular-import issues.
"""

from __future__ import annotations

import io
from typing import Any

import discord

from helpers.embeds import create_embed
from services.ticket_service import TicketService
from utils.logging import get_logger

from helpers.bot_protocol import BotProtocol

logger = get_logger(__name__)


async def _get_staff_and_check(
    bot: BotProtocol,
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
    bot: BotProtocol,
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
