"""
Unified recheck service for user and admin verification rechecks.

This module provides a shared implementation used by:
- User button clicks in Discord (cogs/verification/commands.py)
- Admin dashboard web API (services/internal_api.py)

Ensures consistent behavior: rate limiting, snapshots,
remediation, audit logging.
"""

import time
from typing import TYPE_CHECKING

import discord

from helpers.audit import log_admin_action
from helpers.http_helper import NotFoundError
from helpers.leadership_log import EventType, InitiatorKind, InitiatorSource
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.task_queue import flush_tasks
from helpers.username_404 import handle_username_404
from helpers.verification_logging import log_guild_sync
from services.db.database import Database
from services.guild_sync import apply_state_to_guild
from services.verification_scheduler import (
    compute_next_retry,
    handle_recheck_failure,
    schedule_user_recheck,
)
from services.verification_state import compute_global_state, store_global_state
from utils.logging import get_logger

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = get_logger(__name__)


async def perform_recheck(
    member: discord.Member,
    rsi_handle: str,
    bot: "Bot",
    *,
    initiator_kind: InitiatorKind = InitiatorKind.USER,
    initiator_source: InitiatorSource | None = None,
    admin_user_id: str | None = None,
    admin_display_name: str | None = None,
    enforce_rate_limit: bool = True,
    log_leadership: bool = True,
    log_audit: bool = False,
) -> dict:
    """
    Perform a unified verification recheck with consistent side effects.

    This function orchestrates the full recheck flow:
    1. Rate limiting (optional)
    2. Compute global verification state from RSI API
    3. Apply state to guild (enqueues role/nickname tasks)
    4. 404 remediation if RSI handle not found
    5. Flush task queue (apply role/nickname changes)
    6. Store global state and schedule next recheck
    7. Leadership log (optional)
    8. Admin audit log (optional)

    Args:
        member: Discord member to recheck
        rsi_handle: RSI handle to verify against
        bot: Bot instance with config and services
        initiator_kind: InitiatorKind.USER (button), InitiatorKind.ADMIN (dashboard/bulk), or InitiatorKind.AUTO
        initiator_source: Optional InitiatorSource to distinguish command/web/bulk/voice/auto/button/system
        admin_user_id: Required if initiator_kind="Admin" for audit logging
        admin_display_name: Optional human-friendly admin name for leadership log (not a mention)
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

    initiator_label = initiator_kind.value

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

    start_time = time.time()

    try:
        global_state = await compute_global_state(
            member.id,
            rsi_handle,
            bot.http_client,  # type: ignore[attr-defined]
            config=getattr(bot, "config", {}),
            force_refresh=initiator_kind == InitiatorKind.ADMIN,
        )
    except NotFoundError:
        result["remediated"] = True
        try:
            await handle_username_404(bot, member, rsi_handle)
            await flush_tasks()
        except Exception as e:
            logger.warning(
                f"Unified 404 handler failed ({initiator_label} recheck): {e}"
            )
        result["error"] = "RSI handle not found. User may have changed their handle."
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
    except Exception as e:
        logger.exception(f"Recheck failed ({initiator_label})")
        result["error"] = str(e)
        if log_audit and admin_user_id:
            await log_admin_action(
                admin_user_id=admin_user_id,
                guild_id=str(member.guild.id),
                action="RECHECK_USER",
                target_user_id=str(member.id),
                details={"rsi_handle": rsi_handle, "error": str(e)},
                status="error",
            )
        return result

    if global_state.error:
        fail_count = await Database.get_auto_recheck_fail_count(int(member.id))
        await handle_recheck_failure(
            member.id,
            global_state.error,
            fail_count=fail_count + 1,
            config=getattr(bot, "config", {}),
        )
        result["error"] = global_state.error
        return result

    # Apply to guild BEFORE storing global state so "before" snapshot captures current DB
    guild_result = await apply_state_to_guild(global_state, member.guild, bot)
    await flush_tasks()

    # Now persist the global state after snapshots are taken
    await store_global_state(global_state)

    # Always set status from global_state (it's the source of truth)
    result["status"] = global_state.status

    if guild_result:
        diff_payload = guild_result.diff
        if hasattr(diff_payload, "to_dict"):
            try:
                diff_payload = diff_payload.to_dict()
            except Exception:
                diff_payload = guild_result.diff  # fallback to raw object

        result["diff"] = diff_payload

        if log_leadership:
            await log_guild_sync(
                guild_result,
                EventType.RECHECK,
                bot,
                initiator={
                    "user_id": member.id,
                    "kind": initiator_kind,
                    "source": initiator_source,
                    "name": admin_display_name,
                },
            )

    if enforce_rate_limit:
        await log_attempt(member.id, "recheck")

    next_retry = compute_next_retry(global_state, config=getattr(bot, "config", {}))
    if next_retry:
        await schedule_user_recheck(member.id, next_retry)

    result["success"] = True

    if log_audit and admin_user_id:
        await log_admin_action(
            admin_user_id=admin_user_id,
            guild_id=str(member.guild.id),
            action="RECHECK_USER",
            target_user_id=str(member.id),
            details={
                "rsi_handle": rsi_handle,
                "status": result.get("status"),
                "duration_ms": int((time.time() - start_time) * 1000),
                "diff": result.get("diff"),
            },
            status="success",
        )

    return result
