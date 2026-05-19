import io
import time
from typing import TYPE_CHECKING

import discord

from helpers.bot_utils import get_guild_org_sid
from helpers.constants import DEFAULT_ORG_SID
from helpers.discord_api import channel_send_message
from services.db.repository import BaseRepository
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


# ----------------------------
# Leadership log
# ----------------------------


def canonicalize_status_for_display(status: str) -> str:
    """
    Convert internal status strings to canonical display format.

    Args:
        status: Internal status string (e.g., 'main', 'affiliate', 'non_member', 'unknown')

    Returns:
        Canonical display string: "Main", "Affiliate", or "Not a Member"
    """
    status_normalized = (status or "").lower().strip()

    if status_normalized == "main":
        return "Main"
    elif status_normalized == "affiliate":
        return "Affiliate"
    elif status_normalized in ("non_member", "unknown"):
        return "Not a Member"
    else:
        # Fallback for any unexpected status
        return "Not a Member"


def format_admin_recheck_message(
    admin_display_name: str, user_id: int, old_status: str, new_status: str
) -> tuple[str, bool]:
    """
    Format admin recheck message with exact specification.

    Args:
        admin_display_name: Display name of the admin who initiated the recheck
        user_id: Discord user ID for mention
        old_status: Previous status (internal format)
        new_status: New status (internal format)

    Returns:
        tuple[str, bool]: (formatted_message, changed_bool)
        - formatted_message: The formatted message string
        - changed_bool: True if roles changed, False if no change
    """
    old_pretty = canonicalize_status_for_display(old_status)
    new_pretty = canonicalize_status_for_display(new_status)

    # Determine if there was actually a status change
    changed = old_status != new_status

    # Set emoji and status word based on whether status changed
    if changed:
        emoji = "🔁"
        status_word = "Updated"
        # Two-line format with status change
        message = (
            f"[Admin Check • Admin: {admin_display_name}] <@{user_id}> {emoji} {status_word}\n"
            f"Status: {old_pretty} → {new_pretty}"
        )
    else:
        emoji = "🥺"
        status_word = "No changes"
        # Single-line format for no change
        message = f"[Admin Check • Admin: {admin_display_name}] <@{user_id}> {emoji} {status_word}"

    return message, changed


async def send_admin_recheck_notification(
    bot: "MyBot",
    admin_display_name: str,
    member: discord.Member,
    old_status: str,
    new_status: str,
) -> tuple[bool, bool]:
    """
    Send admin recheck notification to leadership announcements channel.

    Args:
        bot: Bot instance with config service
        admin_display_name: Display name of admin who initiated recheck
        member: Discord member being rechecked
        old_status: Previous status (internal format)
        new_status: New status (internal format)

    Returns:
        tuple[bool, bool]: (success, changed) where success indicates if message was sent and changed indicates if roles changed
    """
    guild = member.guild
    guild_config = bot.services.guild_config

    # Debug-only context without sensitive names
    logger.debug(
        "send_admin_recheck_notification called",
        extra={"user_id": member.id, "guild_id": guild.id},
    )

    # Get leadership announcement channel via config service
    leadership_channel = await guild_config.get_channel(
        guild.id, "leadership_announcement_channel_id", guild
    )

    if not leadership_channel:
        logger.warning(
            f"No leadership_announcement_channel_id configured for guild {guild.id} (admin recheck notification)"
        )
        return False, False

    try:
        message, changed = format_admin_recheck_message(
            admin_display_name=admin_display_name,
            user_id=member.id,
            old_status=old_status,
            new_status=new_status,
        )

        await channel_send_message(leadership_channel, message)

        logger.info(
            f"Admin recheck notification sent to {leadership_channel.name}: {message.replace(chr(10), ' | ')}"
        )

        return True, changed
    except Exception as e:
        logger.warning(f"Failed to send admin recheck notification: {e}")
        return False, False


async def send_verification_announcements(
    bot: "MyBot",
    member: discord.Member,
    old_status: str,
    new_status: str,
    is_recheck: bool,
    by_admin: str | None = None,
):
    """
    Posts verification/re-check logs to leadership channel.
    """
    guild_config = bot.services.guild_config
    guild = member.guild

    lead_channel = await guild_config.get_channel(
        guild.id, "leadership_announcement_channel_id", guild
    )

    if not isinstance(member, discord.Member) or (
        guild and guild.get_member(member.id) is None
    ):
        try:
            member = await guild.fetch_member(member.id)
        except Exception as e:
            logger.warning(f"Failed to fetch full member object for {member.id}: {e}")
            return

    if not lead_channel:
        logger.warning(f"No leadership channel configured for guild {guild.id}")
        return

    old_status = (old_status or "").lower()
    new_status = (new_status or "").lower()

    def status_str(s, org_sid=DEFAULT_ORG_SID):
        """Return formatted status string with organization SID."""
        if s == "main":
            return f"**{org_sid} Main**"
        if s == "affiliate":
            return f"**{org_sid} Affiliate**"
        return "*Not a Member*" if s == "non_member" else str(s)

    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = ""
    if is_recheck and by_admin and by_admin != getattr(member, "display_name", None):
        admin_phrase = f" (**{by_admin}** Initiated)"

    # Fetch organization SID for dynamic status strings
    org_sid = await get_guild_org_sid(bot, member.guild.id, default=DEFAULT_ORG_SID)

    if lead_channel:
        try:
            if is_recheck:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} {log_action}{admin_phrase}: "
                    f"**{status_str(old_status, org_sid)}** → **{status_str(new_status, org_sid)}**",
                )
            else:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} verified as {status_str(new_status, org_sid)}",
                )
        except Exception as e:
            logger.warning(f"Could not send log to leadership channel: {e}")


async def send_admin_bulk_check_summary(
    bot: "MyBot",
    *,
    guild: discord.Guild,
    invoker: discord.Member,
    scope_label: str,
    scope_channel: str | None,
    embed: discord.Embed,
    csv_bytes: bytes,
    csv_filename: str,
) -> dict[str, str]:
    """
    Send bulk verification check summary to leadership/admin announcement channel.

    Posts a single message containing:
    - Detailed embed with requester, scope, channel, counts, and per-user info
    - CSV attachment with complete results

    Args:
        bot: Bot instance with config
        guild: Discord guild
        invoker: Admin who initiated the check
        scope_label: "specific users" | "voice channel" | "all active voice"
        scope_channel: Channel name if applicable (e.g., "#General-Voice")
        embed: Pre-built summary embed
        csv_bytes: CSV file content as bytes
        csv_filename: Filename for the CSV attachment

    Returns:
        Dict with channel metadata for user acknowledgment/logging:
        - name: Channel name (e.g., "leadership-announcements")
        - mention: Channel mention (e.g., "<#1234567890>")

    Raises:
        Exception if channel not configured or message fails to send
    """
    guild_config = bot.services.guild_config

    # Get leadership announcement channel
    channel = await guild_config.get_channel(
        guild.id, "leadership_announcement_channel_id", guild
    )

    if not channel:
        logger.error(
            f"No leadership_announcement_channel_id configured for guild {guild.id}"
        )
        raise ValueError("Leadership announcement channel not configured")

    try:
        # Create CSV file attachment
        csv_file = discord.File(fp=io.BytesIO(csv_bytes), filename=csv_filename)

        # Send embed + CSV to leadership channel (NOT using leadership_log header)
        await channel.send(embed=embed, file=csv_file)

        logger.info(
            f"Bulk check summary posted to #{channel.name} by {invoker.display_name} "
            f"(scope: {scope_label}, checked: {len(csv_bytes)} bytes CSV)"
        )

        return {"name": channel.name, "mention": channel.mention}

    except Exception as e:
        logger.exception(
            f"Failed to send bulk check summary to leadership channel: {e}"
        )
        raise

        # ----------------------------
        # Queue helpers
        # ----------------------------


def _classify_event(old_status: str, new_status: str) -> str | None:
    """
    Map a status transition to an announceable event type.

    Only promotions are announced:
    - non_member → main: "joined_main"
    - non_member → affiliate: "joined_affiliate"
    - affiliate → main: "promoted_to_main"

    Demotions return None (not announced).
    Treats "unknown" as equivalent to "non_member" for classification.

    Args:
        old_status: Previous membership status
        new_status: New membership status

    Returns:
        Event type string for promotions, None for demotions/no-change
    """
    o = (old_status or "").lower().strip()
    n = (new_status or "").lower().strip()

    # Normalize 'unknown' to 'non_member' (defensive edge case handling)
    if o == "unknown":
        o = "non_member"
    if n == "unknown":
        n = "non_member"

    if not o or not n or o == n:
        return None

    # Promotions only
    if n == "main" and o == "non_member":
        return "joined_main"
    if n == "affiliate" and o == "non_member":
        return "joined_affiliate"
    if o == "affiliate" and n == "main":
        return "promoted_to_main"

    # Demotions (main→affiliate, main→non_member, affiliate→non_member) are not announced
    return None


async def enqueue_announcement_for_guild(
    bot,
    member: discord.Member,
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    prev_main_orgs: list[str] | None,
    prev_affiliate_orgs: list[str] | None,
) -> None:
    """
    Guild-aware announcement enqueuing that derives status from org lists.

    Compares previous and current org lists to determine status change for THIS guild's
    tracked organization, then enqueues if it's a promotion (not a demotion).

    Args:
        bot: Bot instance with services
        member: Discord member being verified/rechecked
        main_orgs: Current main organization SIDs
        affiliate_orgs: Current affiliate organization SIDs
        prev_main_orgs: Previous main organization SIDs (None if initial verification)
        prev_affiliate_orgs: Previous affiliate organization SIDs (None if initial verification)
    """
    from services.db.database import derive_membership_status

    try:
        # Get this guild's tracked organization SID
        guild_org_sid = await get_guild_org_sid(bot, member.guild.id)

        # Derive status for this guild before and after
        old_status = derive_membership_status(
            prev_main_orgs, prev_affiliate_orgs, guild_org_sid
        )
        new_status = derive_membership_status(main_orgs, affiliate_orgs, guild_org_sid)

        # Business-level visibility: record the derived transition for this guild
        logger.info(
            "Announcement status check",
            extra={
                "user_id": member.id,
                "guild_id": member.guild.id,
                "old_status": old_status,
                "new_status": new_status,
                "org_sid": guild_org_sid,
            },
        )

        # Enqueue if it's a promotion; also log classification decision
        et = _classify_event(old_status, new_status)
        logger.info(
            "Announcement classification",
            extra={
                "user_id": member.id,
                "guild_id": member.guild.id,
                "old_status": old_status,
                "new_status": new_status,
                "event_type": et,
            },
        )

        if not et:
            return

        await enqueue_verification_event(member, old_status, new_status)

    except Exception as e:
        logger.warning(
            f"Failed to enqueue guild-aware announcement for user {member.id}: {e}"
        )


async def enqueue_verification_event(
    member: discord.Member, old_status: str, new_status: str
):
    """
    Append an announceable verification event to the durable queue.

    Coalescing behavior:
      • Remove any other pending events for this user first (ensures 1 pending/user).
      • Insert only the newest event. This prevents double-announcements
        when a user moves quickly (non_member → affiliate → main).
      • NOTE: Rapid status changes will only announce the FINAL state, not intermediate
        milestones. E.g., non_member → affiliate → main will only announce "promoted_to_main",
        not "joined_affiliate". This is intentional to reduce announcement spam.
    """
    et = _classify_event(old_status, new_status)
    if not et:
        logger.debug(
            f"Status transition not announceable: {old_status} → {new_status}",
            extra={
                "user_id": member.id,
                "guild_id": member.guild.id if member.guild else None,
            },
        )
        return

    now = int(time.time())
    guild_id = member.guild.id if member.guild else None

    if guild_id is None:
        logger.warning(
            f"Cannot enqueue announcement event for user {member.id}: no guild context"
        )
        return

    try:
        async with BaseRepository.transaction() as db:
            # Coalesce: drop older pending events for this user in this guild
            await db.execute(
                "DELETE FROM announcement_events WHERE user_id = ? AND guild_id = ? AND announced_at IS NULL",
                (member.id, guild_id),
            )

            # Insert the latest event with guild_id
            await db.execute(
                (
                    "INSERT INTO announcement_events (user_id, guild_id, old_status, new_status, event_type, created_at, "
                    "announced_at) VALUES (?, ?, ?, ?, ?, ?, NULL)"
                ),
                (
                    member.id,
                    guild_id,
                    (old_status or "non_member"),
                    (new_status or ""),
                    et,
                    now,
                ),
            )
            await db.commit()
            logger.info(
                "Announcement queued",
                extra={
                    "user_id": member.id,
                    "guild_id": guild_id,
                    "event_type": et,
                },
            )
    except Exception as e:
        logger.warning(
            f"Failed to enqueue announcement event for user {member.id} in guild {guild_id}: {e}"
        )

        # ----------------------------
        # Bulk Announcer v2 (queue-driven)
        # ----------------------------

# Re-export BulkAnnouncer for backward compatibility
from helpers.announcement_bulk_cog import BulkAnnouncer  # noqa: F401
