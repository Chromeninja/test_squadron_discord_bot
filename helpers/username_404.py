import time
import discord
from helpers.database import Database
from helpers.logger import get_logger
from helpers.task_queue import enqueue_task
from helpers.discord_api import channel_send_message

logger = get_logger(__name__)

MANAGED_ROLE_KEYS = [
    "BOT_VERIFIED_ROLE_ID",
    "MAIN_ROLE_ID",
    "AFFILIATE_ROLE_ID",
    "NON_MEMBER_ROLE_ID",
]


def _gather_managed_roles(bot, member: discord.Member):
    roles = []
    for key in MANAGED_ROLE_KEYS:
        rid = getattr(bot, key, None)
        if not rid:
            continue
        role = bot.role_cache.get(rid) or (member.guild.get_role(rid) if member.guild else None)
        if role:
            roles.append(role)
    return roles


async def remove_bot_roles(member: discord.Member, bot):
    """Remove managed roles from member if present (idempotent)."""
    managed_roles = _gather_managed_roles(bot, member)
    roles_to_remove = [r for r in managed_roles if r in member.roles]

    if not roles_to_remove:
        return False

    async def task():
        try:
            await member.remove_roles(*roles_to_remove, reason="Handle 404 reverify required")
            logger.info(
                "Removed managed roles after 404.",
                extra={
                    "user_id": member.id,
                    "roles_removed": [r.name for r in roles_to_remove],
                },
            )
        except Exception as e:
            logger.warning(f"Failed removing roles for {member.id}: {e}")

    await enqueue_task(task)
    return True


async def handle_username_404(bot, member: discord.Member, old_handle: str):
    """Unified, idempotent 404 handler.

    1. Flag needs_reverify in DB (early exit if already flagged)
    2. Remove managed roles
    3. Post one spam channel alert & leadership alert
    4. Unschedule auto rechecks
    5. Structured logging
    """
    now = int(time.time())
    try:
        newly_flagged = await Database.flag_needs_reverify(member.id, now)
    except Exception as e:
        logger.error(
            "Failed to flag needs_reverify",
            extra={"user_id": member.id, "rsi_handle": old_handle, "error": str(e)},
        )
        return False

    if not newly_flagged:
        # Dedup hit; already handled before.
        logger.info(
            "Handle 404 deduplicated.",
            extra={
                "user_id": member.id,
                "rsi_handle": old_handle,
                "dedup": True,
                "actions": ["already_flagged"],
            },
        )
        return False

    # Stop auto rechecks
    try:
        await Database.unschedule_auto_recheck(member.id)
    except Exception as e:
        logger.warning(f"Failed unscheduling auto recheck for {member.id}: {e}")

    roles_removed = await remove_bot_roles(member, bot)

    # Announcements
    spam_channel = (
        bot.get_channel(getattr(bot, "BOT_SPAM_CHANNEL_ID", None))
        if getattr(bot, "BOT_SPAM_CHANNEL_ID", None)
        else None
    )
    verification_channel_id = getattr(bot, "VERIFICATION_CHANNEL_ID", 0)
    # Exact copy per spec
    spam_msg = (
        f"{member.mention} it seems your handle has changed, please navigate to <#{verification_channel_id}> and reverify your account. Your roles have been revoked."
    )
    lead_msg = (
        f"{member.mention} handle `{old_handle}` is pulling a 404 — roles have been removed and the user has been alerted."
    )
    if spam_channel:
        try:
            await channel_send_message(spam_channel, spam_msg)
        except Exception as e:
            logger.warning(f"Failed sending spam alert for {member.id}: {e}")
    # Leadership channel log (reuse existing announcement path by direct send)
    try:
        lead_channel_id = (bot.config or {}).get("channels", {}).get("leadership_announcement_channel_id")
        if lead_channel_id:
            lead_channel = member.guild.get_channel(lead_channel_id)
            if lead_channel:
                await channel_send_message(lead_channel, lead_msg)
    except Exception as e:
        logger.warning(f"Failed sending leadership 404 alert for {member.id}: {e}")

    logger.info(
        "Handle 404 handled.",
        extra={
            "user_id": member.id,
            "rsi_handle": old_handle,
            "dedup": False,
            "actions": [
                "flagged_db",
                "roles_removed" if roles_removed else "roles_none",
                "spam_alert" if spam_channel else "spam_missing",
                "leadership_alert" if lead_channel_id else "leadership_missing",
            ],
            "channels": {
                "spam": getattr(bot, "BOT_SPAM_CHANNEL_ID", None),
                "leadership": lead_channel_id,
                "verification": verification_channel_id,
            },
        },
    )
    return True
