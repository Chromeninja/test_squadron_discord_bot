"""
Unified recheck service for user and admin verification rechecks.

This module provides a shared implementation used by:
- User button clicks in Discord (cogs/verification/commands.py)
- Admin dashboard web API (services/internal_api.py)

Ensures consistent behavior: rate limiting, snapshots,
remediation, audit logging.
"""

import time
from dataclasses import asdict as _asdict
from typing import TYPE_CHECKING, Literal, cast

import discord

from helpers.audit import log_admin_action
from helpers.http_helper import NotFoundError
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.role_helper import reverify_member
from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import flush_tasks
from helpers.username_404 import handle_username_404
from utils.logging import get_logger

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = get_logger(__name__)


async def perform_recheck(
    member: discord.Member,
    rsi_handle: str,
    bot: "Bot",
    *,
    initiator_kind: str = "User",
    admin_user_id: str | None = None,
    enforce_rate_limit: bool = True,
    log_leadership: bool = True,
    log_audit: bool = False,
) -> dict:
    """
    Perform a unified verification recheck with consistent side effects.

    This function orchestrates the full recheck flow:
    1. Rate limiting (optional)
    2. Before snapshot
    3. Call reverify_member (enqueues role/nickname tasks)
    4. 404 remediation if RSI handle not found
    5. Flush task queue (apply role/nickname changes)
    6. After snapshot + diff
    7. Leadership log (optional)
    8. Admin audit log (optional)

    Args:
        member: Discord member to recheck
        rsi_handle: RSI handle to verify against
        bot: Bot instance with config and services
        initiator_kind: "User" (button), "Admin" (dashboard), or "System" (auto)
        admin_user_id: Required if initiator_kind="Admin" for audit logging
        enforce_rate_limit: If True, check and log rate limit attempts
        log_leadership: If True, post leadership log with before/after diff
        log_audit: If True, log to admin_action_log table

    Returns:
        dict with keys:
            - success (bool): True if recheck succeeded
            - error (str | None): Error message if failed
            - rate_limited (bool): True if rate limit prevented recheck
            - wait_until (int | None): Unix timestamp when rate limit expires
            - status (str | None): Verification status
              ("main", "affiliate", "non_member")
            - diff (dict | None): Before/after snapshot diff
            - remediated (bool): True if 404 remediation was triggered
    """
    result = {
        "success": False,
        "error": None,
        "rate_limited": False,
        "wait_until": None,
        "status": None,
        "diff": None,
        "remediated": False,
    }

    # Rate limiting
    if enforce_rate_limit:
        rate_limited, wait_until = await check_rate_limit(member.id, "recheck")
        if rate_limited:
            result["rate_limited"] = True
            result["wait_until"] = wait_until
            result["error"] = f"Rate limited until {wait_until}"

            # Log rate-limited admin action
            if log_audit and admin_user_id:
                await log_admin_action(
                    admin_user_id=admin_user_id,
                    guild_id=str(member.guild.id),
                    action="RECHECK_USER",
                    target_user_id=str(member.id),
                    details={"rsi_handle": rsi_handle, "rate_limited": True},
                    status="rate_limited",
                )

            return result

    # Snapshot BEFORE reverify
    start_time = time.time()
    before_snap = await snapshot_member_state(bot, member)

    # Attempt re-verification (DB + role/nick tasks enqueued)
    try:
        reverify_result = await reverify_member(member, rsi_handle, bot)
    except NotFoundError:
        # Invoke unified remediation
        result["remediated"] = True
        try:
            await handle_username_404(bot, member, rsi_handle)
        except Exception as e:
            logger.warning(
                f"Unified 404 handler failed ({initiator_kind} recheck): {e}"
            )

        result["error"] = "RSI handle not found. User may have changed their handle."

        # Log failed admin action with remediation
        if log_audit and admin_user_id:
            await log_admin_action(
                admin_user_id=admin_user_id,
                guild_id=str(member.guild.id),
                action="RECHECK_USER",
                target_user_id=str(member.id),
                details={"rsi_handle": rsi_handle, "remediated": True},
                status="error",
            )

        return result
    except Exception:
        logger.exception(f"Recheck failed ({initiator_kind})")
        result["error"] = "Recheck failed due to internal error"

        # Log failed admin action
        if log_audit and admin_user_id:
            await log_admin_action(
                admin_user_id=admin_user_id,
                guild_id=str(member.guild.id),
                action="RECHECK_USER",
                target_user_id=str(member.id),
                details={"rsi_handle": rsi_handle, "error": "internal_error"},
                status="error",
            )

        return result

    # Parse reverify result
    success, status_info, message = reverify_result
    if not success:
        result["error"] = message or "Re-check failed. Please try again later."

        # Log failed admin action
        if log_audit and admin_user_id:
            await log_admin_action(
                admin_user_id=admin_user_id,
                guild_id=str(member.guild.id),
                action="RECHECK_USER",
                target_user_id=str(member.id),
                details={"rsi_handle": rsi_handle, "message": message},
                status="error",
            )

        return result

    # Extract status
    if isinstance(status_info, tuple):
        _old_status, new_status = status_info
    else:
        new_status = status_info

    result["status"] = new_status
    result["success"] = True

    # Log rate limit attempt
    if enforce_rate_limit:
        await log_attempt(member.id, "recheck")

    # Flush task queue to apply role/nickname changes
    try:
        await flush_tasks()
    except Exception as e:
        logger.debug(f"Failed to flush task queue: {e}")

    # Refetch member to get latest nickname/roles after queued tasks applied
    try:
        refreshed = await member.guild.fetch_member(member.id)
        if refreshed:
            member = refreshed
    except Exception as e:
        logger.debug(f"Failed to refetch member: {e}")

    # Snapshot AFTER reverify and compute diff
    after_snap = await snapshot_member_state(bot, member)
    diff = diff_snapshots(before_snap, after_snap)

    # Adjust diff for nickname changes if flag set
    try:
        if diff.get("username_before") == diff.get("username_after") and getattr(
            member, "_nickname_changed_flag", False
        ):
            pref = getattr(member, "_preferred_verification_nick", None)
            if pref and pref != diff.get("username_before"):
                diff["username_after"] = pref
    except Exception as e:
        logger.debug(f"Failed to adjust nickname diff: {e}")

    # Store a JSON-serializable dict for API responses
    try:
        result["diff"] = diff.to_dict()  # MemberSnapshotDiff implements to_dict()
    except Exception:
        # Fallback: best-effort dataclass conversion
        try:
            result["diff"] = _asdict(diff)
        except Exception as e:
            logger.debug(f"Failed to serialize diff: {e}")
            result["diff"] = None

    # Leadership log
    if log_leadership:
        try:
            # Cast to Literal type for ChangeSet type safety
            initiator_literal = cast('Literal["User", "Admin", "Auto"]', initiator_kind)
            cs = ChangeSet(
                user_id=member.id,
                event=EventType.RECHECK,
                initiator_kind=initiator_literal,
                initiator_name=admin_user_id if initiator_kind == "Admin" else None,
                notes=None,
                guild_id=member.guild.id if member.guild else None,
            )
            # Apply diff fields (MemberSnapshotDiff implements items())
            try:
                iterable = None
                if hasattr(diff, "items"):
                    iterable = diff.items()
                else:
                    diff_dict = (
                        result.get("diff")
                        if isinstance(result.get("diff"), dict)
                        else None
                    )
                    if diff_dict:
                        iterable = diff_dict.items()
                if iterable:
                    for k, v in iterable:
                        setattr(cs, k, v)
            except Exception as e:
                logger.debug(f"Failed to attach diff to ChangeSet: {e}")
            await post_if_changed(bot, cs)
        except Exception as e:
            logger.debug(f"Leadership log post failed ({initiator_kind} recheck): {e}")

    # Admin audit log
    if log_audit and admin_user_id:
        await log_admin_action(
            admin_user_id=admin_user_id,
            guild_id=str(member.guild.id),
            action="RECHECK_USER",
            target_user_id=str(member.id),
            details={
                "rsi_handle": rsi_handle,
                "status": new_status,
                "duration_ms": int((time.time() - start_time) * 1000),
                "diff": diff.to_dict() if hasattr(diff, "to_dict") else None,
            },
            status="success",
        )

    return result
