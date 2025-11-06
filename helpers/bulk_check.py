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
    # RSI recheck fields (optional)
    rsi_status: str | None = None  # "main" | "affiliate" | "non_member" | "unknown"
    rsi_checked_at: int | None = None  # Unix timestamp
    rsi_error: str | None = None  # Error message if RSI check failed


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


def _count_membership_statuses(rows: list[StatusRow]) -> dict[str, int]:
    """Count rows by membership status category."""
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
    
    return counts


def _format_status_display(membership_status: str) -> str:
    """Convert membership status code to display string."""
    status_map = {
        "main": "Verified/Main",
        "affiliate": "Affiliate",
        "non_member": "Non-Member",
        "unknown": "Unverified",
        "unverified": "Unverified",
    }
    return status_map.get(membership_status, "Not in DB")


def _truncate_text(text: str, max_length: int = 20) -> str:
    """Truncate text if longer than max_length, adding ellipsis."""
    if len(text) > max_length:
        return text[:max_length - 3] + "..."
    return text


def _format_timestamp(timestamp: int | None) -> str:
    """Format Unix timestamp for Discord display."""
    if timestamp and timestamp > 0:
        return f"<t:{timestamp}:R>"
    return "Never"


def _build_description_lines(
    invoker: discord.Member,
    total_processed: int,
    counts: dict[str, int],
    scope_label: str | None = None,
    scope_channel: str | None = None
) -> list[str]:
    """Build description lines with requester info, scope, and status counts."""
    desc_lines = [
        f"**Requested by:** {invoker.mention} (Admin)"
    ]
    
    if scope_label:
        desc_lines.append(f"**Scope:** {scope_label}")
    
    if scope_channel:
        desc_lines.append(f"**Channel:** {scope_channel}")
    
    desc_lines.extend([
        f"**Checked:** {total_processed} users",
        ""  # Blank line before counts
    ])
    
    # Add non-zero status counts
    for category, count in counts.items():
        if count > 0:
            desc_lines.append(f"**{category}:** {count}")
    
    return desc_lines


def _format_detail_line(row: StatusRow) -> str:
    """Format a single row into a detail line for the embed."""
    status = _format_status_display(row.membership_status)
    rsi_display = _truncate_text(row.rsi_handle or "—")
    vc_display = _truncate_text(row.voice_channel or "—")
    updated_display = _format_timestamp(row.last_updated)
    
    # If no RSI recheck data, return DB-only format
    if row.rsi_status is None:
        return f"• <@{row.user_id}> — {status} | RSI: {rsi_display} | VC: {vc_display} | Updated: {updated_display}"
    
    # Include RSI recheck data
    rsi_status_display = _format_status_display(row.rsi_status)
    rsi_checked_display = _format_timestamp(row.rsi_checked_at)
    return (
        f"• <@{row.user_id}> — DB: {status} → RSI: {rsi_status_display} | "
        f"Handle: {rsi_display} | VC: {vc_display} | RSI Checked: {rsi_checked_display}"
    )


def _build_detail_lines(rows: list[StatusRow], max_field_length: int = 1000) -> tuple[list[str], int]:
    """
    Build per-user detail lines, truncating if necessary.
    
    Returns:
        Tuple of (detail_lines, truncated_count)
    """
    detail_lines = []
    field_value_length = 0
    truncated_count = 0
    
    for i, row in enumerate(rows):
        detail_line = _format_detail_line(row)
        
        # Check if adding this line would exceed the limit
        test_length = field_value_length + len(detail_line) + 1  # +1 for newline
        if test_length > max_field_length:
            remaining_count = len(rows) - i
            if remaining_count > 0:
                truncated_count = remaining_count
            break
        
        detail_lines.append(detail_line)
        field_value_length = test_length
    
    return detail_lines, truncated_count


def build_summary_embed(
    *,
    invoker: discord.Member,
    members: list[discord.Member],
    rows: list[StatusRow],
    truncated_count: int = 0,
    scope_label: str | None = None,
    scope_channel: str | None = None
) -> discord.Embed:
    """
    Create a Discord embed for bulk verification check results posted to leadership channel.
    
    Always includes full details with dynamic truncation to fit Discord limits.
    """
    # Count statuses and build embed
    counts = _count_membership_statuses(rows)
    
    embed = discord.Embed(
        title="Bulk Verification Check",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    # Build description with metadata and counts
    desc_lines = _build_description_lines(
        invoker, len(rows), counts, scope_label, scope_channel
    )
    embed.description = "\n".join(desc_lines)
    
    # Add per-user details with truncation
    if rows:
        detail_lines, additional_truncated = _build_detail_lines(rows)
        truncated_count = max(truncated_count, additional_truncated)
        
        if detail_lines:
            embed.add_field(
                name="Details",
                value="\n".join(detail_lines),
                inline=False
            )
    
    # Add footer if truncated
    if truncated_count > 0:
        embed.set_footer(text=f"… and {truncated_count} more (see CSV for full results)")
    
    return embed


async def write_csv(
    rows: list[StatusRow],
    *,
    guild_name: str = "guild",
    invoker_name: str = "admin"
) -> tuple[str, bytes]:
    """
    Generate CSV export of verification status rows.
    
    Returns:
        Tuple of (filename, content_bytes) ready for discord.File.
        Filename format: verify_bulk_{guild}_{YYYYMMDD_HHMM}_{invoker}.csv
    """
    if not rows:
        # Empty results
        timestamp_str = time.strftime("%Y%m%d_%H%M", time.gmtime())
        safe_guild = re.sub(r'[^\w\-]', '_', guild_name)[:30]
        safe_invoker = re.sub(r'[^\w\-]', '_', invoker_name)[:20]
        filename = f"verify_bulk_{safe_guild}_{timestamp_str}_{safe_invoker}.csv"
        return filename, b"user_id,username,rsi_handle,membership_status,last_updated,voice_channel,rsi_status,rsi_checked_at,rsi_error\n"

    # Generate filename with timestamp and invoker
    timestamp_str = time.strftime("%Y%m%d_%H%M", time.gmtime())
    # Sanitize guild and invoker names for filename
    safe_guild = re.sub(r'[^\w\-]', '_', guild_name)[:30]
    safe_invoker = re.sub(r'[^\w\-]', '_', invoker_name)[:20]
    filename = f"verify_bulk_{safe_guild}_{timestamp_str}_{safe_invoker}.csv"

    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header (include RSI recheck fields)
    writer.writerow([
        "user_id",
        "username",
        "rsi_handle",
        "membership_status",
        "last_updated",
        "voice_channel",
        "rsi_status",
        "rsi_checked_at",
        "rsi_error"
    ])

    # Write data rows
    for row in rows:
        writer.writerow([
            row.user_id,
            row.username,
            row.rsi_handle or "",
            row.membership_status or "",
            row.last_updated or "",
            row.voice_channel or "",
            row.rsi_status or "",
            row.rsi_checked_at or "",
            row.rsi_error or ""
        ])

    # Get bytes content
    csv_content = output.getvalue()
    content_bytes = csv_content.encode('utf-8')

    return filename, content_bytes
