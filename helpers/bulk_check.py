# helpers/bulk_check.py

import csv
import io
import re
import time
from collections.abc import Iterable
from typing import NamedTuple

import discord

from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)


class StatusRow(NamedTuple):
    user_id: int
    username: str
    rsi_handle: str | None
    membership_status: str | None
    last_updated: int | None
    voice_channel: str | None


MENTION_RE = re.compile(r"<@!?(?P<id>\d+)>|(?P<raw>\d{15,20})")


async def parse_members_text(guild: discord.Guild, text: str) -> list[discord.Member]:
    """Parse multiple mentions/IDs from a single string; dedupe; return members present in guild."""
    member_ids = set()

    # Extract all user IDs from mentions and raw numbers
    for match in MENTION_RE.finditer(text):
        if match.group("id"):
            member_ids.add(int(match.group("id")))
        elif match.group("raw"):
            member_ids.add(int(match.group("raw")))

    members = []
    for user_id in member_ids:
        try:
            # Try to get member from cache first
            member = guild.get_member(user_id)
            if member is None:
                # Fall back to fetching from API
                member = await guild.fetch_member(user_id)
            if member:
                members.append(member)
        except (discord.NotFound, discord.HTTPException):
            # Member not found or other API error, skip
            logger.debug(f"Could not find member with ID {user_id} in guild {guild.id}")
            continue

    return members


async def collect_targets(
    targets: str,
    guild: discord.Guild,
    members_text: str | None,
    channel: discord.VoiceChannel | None
) -> list[discord.Member]:
    """Return ordered unique members according to targets mode."""
    if targets == "users":
        if not members_text:
            return []
        return await parse_members_text(guild, members_text)

    elif targets == "voice_channel":
        if not channel:
            return []
        return list(channel.members)

    elif targets == "active_voice":
        # Collect all members from all non-empty voice channels
        all_members = set()
        for voice_channel in guild.voice_channels:
            if voice_channel.members:  # Skip empty channels
                all_members.update(voice_channel.members)
        return list(all_members)

    else:
        return []


async def fetch_status_rows(members: Iterable[discord.Member]) -> list[StatusRow]:
    """Batch DB read for verification rows; join with current voice channel if any."""
    if not members:
        return []

    member_list = list(members)
    user_ids = [m.id for m in member_list]

    # Build a mapping from user_id to member for quick lookup
    member_map = {m.id: m for m in member_list}

    async with Database.get_connection() as db:
        # Fetch verification data for all users at once
        placeholders = ",".join("?" * len(user_ids))
        query = f"""
            SELECT user_id, rsi_handle, membership_status, last_updated
            FROM verification
            WHERE user_id IN ({placeholders})
        """

        cursor = await db.execute(query, user_ids)
        rows = await cursor.fetchall()

    # Build a map of verification data keyed by user_id
    verification_map = {}
    for row in rows:
        user_id, rsi_handle, membership_status, last_updated = row
        verification_map[user_id] = {
            "rsi_handle": rsi_handle,
            "membership_status": membership_status,
            "last_updated": last_updated
        }

    # Build the final result rows
    status_rows = []
    for member in member_list:
        # Get verification data or defaults
        verification_data = verification_map.get(member.id, {})
        rsi_handle = verification_data.get("rsi_handle")
        membership_status = verification_data.get("membership_status")
        last_updated = verification_data.get("last_updated")

        # Get current voice channel name
        voice_channel_name = None
        if member.voice and member.voice.channel:
            voice_channel_name = member.voice.channel.name

        # Use display_name for consistency with Discord UI
        username = member.display_name

        status_rows.append(StatusRow(
            user_id=member.id,
            username=username,
            rsi_handle=rsi_handle,
            membership_status=membership_status,
            last_updated=last_updated,
            voice_channel=voice_channel_name
        ))

    return status_rows


def build_summary_embed(
    *,
    invoker: discord.Member,
    members: list[discord.Member],
    rows: list[StatusRow],
    show_details: bool,
    truncated_count: int = 0
) -> discord.Embed:
    """Create a Discord-appropriate embed with counts and dynamic truncation to fit Discord limits."""

    # Count by membership status
    counts = {
        "Verified/Main": 0,
        "Affiliate": 0,
        "Non-Member": 0,
        "Unverified": 0,
        "Not in DB": 0
    }

    for row in rows:
        if row.membership_status == "main":
            counts["Verified/Main"] += 1
        elif row.membership_status == "affiliate":
            counts["Affiliate"] += 1
        elif row.membership_status == "non_member":
            counts["Non-Member"] += 1
        elif row.membership_status in ("unknown", "unverified"):
            counts["Unverified"] += 1
        else:
            counts["Not in DB"] += 1

    # Build embed
    embed = discord.Embed(
        title="🔎 Verification Status Check",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )

    # Description with summary
    total_processed = len(rows)
    summary_lines = [f"**Total processed:** {total_processed}"]

    for category, count in counts.items():
        if count > 0:
            summary_lines.append(f"**{category}:** {count}")

    embed.description = "\n".join(summary_lines)

    # Add details if requested and not too many
    if show_details and rows:
        detail_lines = []
        field_value_length = 0
        max_field_length = 1000  # Leave some buffer below Discord's 1024 limit
        
        for i, row in enumerate(rows):
            # Format status for display
            if row.membership_status == "main":
                status = "Verified/Main"
            elif row.membership_status == "affiliate":
                status = "Affiliate"
            elif row.membership_status == "non_member":
                status = "Non-Member"
            elif row.membership_status in ("unknown", "unverified"):
                status = "Unverified"
            else:
                status = "Not in DB"

            # Format RSI handle (truncate if too long)
            rsi_display = row.rsi_handle if row.rsi_handle else "—"
            if len(rsi_display) > 20:
                rsi_display = rsi_display[:17] + "..."

            # Format voice channel (truncate if too long)
            vc_display = row.voice_channel if row.voice_channel else "—"
            if len(vc_display) > 20:
                vc_display = vc_display[:17] + "..."

            # Format last updated time
            if row.last_updated and row.last_updated > 0:
                updated_display = f"<t:{row.last_updated}:R>"
            else:
                updated_display = "Never"

            # Build the line
            detail_line = f"• <@{row.user_id}> — {status} | RSI: {rsi_display} | VC: {vc_display} | Updated: {updated_display}"
            
            # Check if adding this line would exceed the limit
            test_length = field_value_length + len(detail_line) + 1  # +1 for newline
            if test_length > max_field_length:
                # Add a truncation message if we're stopping early
                remaining_count = len(rows) - i
                if remaining_count > 0:
                    truncated_count = max(truncated_count, remaining_count)
                break
            
            detail_lines.append(detail_line)
            field_value_length = test_length

        if detail_lines:
            embed.add_field(
                name="Details",
                value="\n".join(detail_lines),
                inline=False
            )

    # Footer with additional info
    footer_parts = []
    if truncated_count > 0:
        footer_parts.append(f"… and {truncated_count} more")
        footer_parts.append("Use export_csv for full results")

    if footer_parts:
        embed.set_footer(text=" | ".join(footer_parts))

    return embed


async def write_csv(rows: list[StatusRow]) -> tuple[str, bytes]:
    """Return (filename, content_bytes) ready for discord.File."""
    if not rows:
        return "verification_status_empty.csv", b"user_id,username,rsi_handle,membership_status,voice_channel,last_updated\n"

    # Generate filename with timestamp
    timestamp = int(time.time())
    filename = f"verification_status_{timestamp}.csv"

    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "user_id",
        "username",
        "rsi_handle",
        "membership_status",
        "voice_channel",
        "last_updated"
    ])

    # Write data rows
    for row in rows:
        writer.writerow([
            row.user_id,
            row.username,
            row.rsi_handle or "",
            row.membership_status or "",
            row.voice_channel or "",
            row.last_updated or ""
        ])

    # Get bytes content
    csv_content = output.getvalue()
    content_bytes = csv_content.encode('utf-8')

    return filename, content_bytes
