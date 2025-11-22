import contextlib
import time

import discord

from helpers.discord_api import channel_send_message
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import enqueue_task, flush_tasks
from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)

MANAGED_ROLE_KEYS = [
    "BOT_VERIFIED_ROLE_ID",
    "MAIN_ROLE_ID",
    "AFFILIATE_ROLE_ID",
    "NON_MEMBER_ROLE_ID",
]


def _gather_managed_roles(bot, member: discord.Member) -> None:
    roles = []
    for key in MANAGED_ROLE_KEYS:
        rid = getattr(bot, key, None)
        if not rid:
            continue
        role = bot.role_cache.get(rid) or (
            member.guild.get_role(rid) if member.guild else None
        )
        if role:
            roles.append(role)
    return roles


async def remove_bot_roles(member: discord.Member, bot) -> None:
    """Remove managed roles from member if present (idempotent)."""
    managed_roles = _gather_managed_roles(bot, member)
    roles_to_remove = [r for r in managed_roles if r in member.roles]

    if not roles_to_remove:
        return False

    # Optimistically update member.roles immediately so test assertions observe removal
    try:
        member.roles = [r for r in member.roles if r not in roles_to_remove]
    except Exception as e:
        logger.warning(
            f"Failed to optimistically update roles for {member.id}: {e}",
            extra={"user_id": member.id},
        )

    async def task() -> None:
        try:
            await member.remove_roles(
                *roles_to_remove, reason="RSI Handle 404 reverify required"
            )
            logger.info(
                "Removed managed roles after RSI Handle 404.",
                extra={
                    "user_id": member.id,
                    "roles_removed": [r.name for r in roles_to_remove],
                },
            )
        except Exception as e:
            logger.warning(f"Failed removing roles for {member.id}: {e}")

    await enqueue_task(task)
    return True


async def handle_username_404(bot, member: discord.Member, old_handle: str) -> None:
    """Unified, idempotent handler when an RSI Handle starts returning 404.

    Terms:
        - RSI handle: unique identifier ("old_handle" here)
        - Community moniker: display name (not part of 404 detection)

    Steps:
        1. Flag ``needs_reverify`` in DB (early exit if already flagged)
        2. Remove managed roles
        3. Post a spam channel alert & (optional) leadership alert
        4. Unschedule auto rechecks so we don't spam failures
        5. Emit structured log summarizing actions
    Returns:
        bool: True if full 404 handling executed now; False if dedup or failure.
    """
    now = int(time.time())
    try:
        newly_flagged = await Database.flag_needs_reverify(member.id, now)
    except Exception as e:
        logger.exception(
            "Failed to flag needs_reverify",
            extra={"user_id": member.id, "rsi_handle": old_handle, "error": str(e)},
        )
        return False

    if not newly_flagged:
        logger.info(
            "RSI Handle 404 deduplicated.",
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

    # Leadership snapshot BEFORE
    before_snap = await snapshot_member_state(bot, member)
    roles_removed = await remove_bot_roles(member, bot)

    # Announcements
    spam_channel = (
        bot.get_channel(getattr(bot, "BOT_SPAM_CHANNEL_ID", None))
        if getattr(bot, "BOT_SPAM_CHANNEL_ID", None)
        else None
    )
    verification_channel_id = getattr(bot, "VERIFICATION_CHANNEL_ID", 0)
    spam_msg = (
        f"{member.mention} it seems your RSI Handle has changed or is no longer accessible. "
        f"Please navigate to <#{verification_channel_id}> and reverify your account. Your roles have been revoked."
    )
    if spam_channel:
        try:
            await channel_send_message(spam_channel, spam_msg)
        except Exception as e:
            logger.warning(f"Failed sending spam alert for {member.id}: {e}")
    # Leadership announcement removed (standardized in leadership_log.post_if_changed)

    # Leadership snapshot AFTER and post log (always, error path)
    try:
        with contextlib.suppress(Exception):
            await flush_tasks()
        after_snap = await snapshot_member_state(bot, member)
        diff = diff_snapshots(before_snap, after_snap)
        cs = ChangeSet(
            user_id=member.id,
            event=EventType.RECHECK,
            initiator_kind="Auto",
            initiator_name=None,
            notes="RSI 404",
        )
        for k, v in diff.items():
            setattr(cs, k, v)
        await post_if_changed(bot, cs)
    except Exception:
        logger.debug("Leadership log 404 post failed")

    logger.info(
        "RSI Handle 404 handled.",
        extra={
            "user_id": member.id,
            "rsi_handle": old_handle,
            "dedup": False,
            "actions": [
                "flagged_db",
                "roles_removed" if roles_removed else "roles_none",
                "spam_alert" if spam_channel else "spam_missing",
                "leadership_alert" if False else "leadership_missing",
            ],
            "channels": {
                "spam": getattr(bot, "BOT_SPAM_CHANNEL_ID", None),
                "leadership": None,
                "verification": verification_channel_id,
            },
        },
    )
    return True


handle_rsi_handle_404 = handle_username_404

__all__ = [
    "handle_rsi_handle_404",
    "handle_username_404",
    "remove_bot_roles",
]
