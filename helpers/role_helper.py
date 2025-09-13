# Helpers/role_helper.py

import contextlib
import random
import time

import discord

from helpers.announcement import enqueue_verification_event
from helpers.discord_api import add_roles, edit_member, remove_roles
from helpers.task_queue import enqueue_task
from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)


def _compute_next_recheck(bot, new_status: str, now: int) -> int:
    cfg = (bot.config or {}).get("auto_recheck", {}) or {}
    cadence_map = cfg.get("cadence_days") or {}
    jitter_h = int(cfg.get("jitter_hours") or 0)
    days = int(cadence_map.get(new_status or "", 0))  # Default 0 -> skip if unknown
    if days <= 0:
        return 0
    jitter = random.randint(-jitter_h * 3600, jitter_h * 3600) if jitter_h > 0 else 0
    return now + days * 86400 + jitter


async def assign_roles(
    member: discord.Member,
    verify_value: int,
    cased_handle: str,
    bot,
    community_moniker: str | None = None,
) -> None:
    """Assign roles based on verification status.

    Args:
        member: Discord member to assign roles to
        verify_value: Verification status (0, 1, 2)
        cased_handle: Properly cased RSI handle
        bot: Bot instance with role_cache and other attributes
        community_moniker: Optional community moniker

    Raises:
        TypeError: If bot parameter is not a proper Bot instance
    """
    from utils.logging import get_logger

    logger = get_logger(__name__)

    # Type validation at service boundary
    if isinstance(bot, str):
        error_msg = f"assign_roles received string '{bot}' instead of Bot instance. Check caller implementation."
        logger.error(
            error_msg, extra={"user_id": member.id, "cased_handle": cased_handle}
        )
        raise TypeError(error_msg)

    if not hasattr(bot, "role_cache"):
        error_msg = f"Bot instance passed to assign_roles lacks role_cache attribute. Type: {type(bot).__name__}"
        logger.error(
            error_msg, extra={"user_id": member.id, "cased_handle": cased_handle}
        )
        raise TypeError(error_msg)

    # Fetch previous status before DB update
    prev_status = None
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT membership_status FROM verification WHERE user_id = ?", (member.id,)
        )
        row = await cursor.fetchone()
        if row:
            prev_status = row[0]

    bot_verified_role = bot.role_cache.get(bot.BOT_VERIFIED_ROLE_ID)
    main_role = bot.role_cache.get(bot.MAIN_ROLE_ID)
    affiliate_role = bot.role_cache.get(bot.AFFILIATE_ROLE_ID)
    non_member_role = bot.role_cache.get(bot.NON_MEMBER_ROLE_ID)

    roles_to_add = []
    roles_to_remove = []
    assigned_role_type = "unknown"

    if bot_verified_role and bot_verified_role not in member.roles:
        roles_to_add.append(bot_verified_role)
        logger.debug(f"Appending role to add: {bot_verified_role.name}")

    if verify_value == 1 and main_role:
        roles_to_add.append(main_role)
        assigned_role_type = "main"
        logger.debug(f"Appending role to add: {main_role.name}")
    elif verify_value == 2 and affiliate_role:
        roles_to_add.append(affiliate_role)
        assigned_role_type = "affiliate"
        logger.debug(f"Appending role to add: {affiliate_role.name}")
    elif verify_value == 0 and non_member_role:
        roles_to_add.append(non_member_role)
        assigned_role_type = "non_member"
        logger.debug(f"Appending role to add: {non_member_role.name}")

        # Map verify_value to membership status
    membership_status_map = {
        1: "main",
        2: "affiliate",
        0: "non_member",
    }
    membership_status = membership_status_map.get(verify_value, "unknown")

    # Update DB
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT INTO verification (user_id, rsi_handle, membership_status, last_updated, community_moniker)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                rsi_handle = excluded.rsi_handle,
                membership_status = excluded.membership_status,
                last_updated = excluded.last_updated,
                community_moniker = excluded.community_moniker,
                -- Only clear needs_reverify if it was previously set (successful re-verification)
                needs_reverify = CASE WHEN verification.needs_reverify = 1 THEN 0 ELSE verification.needs_reverify END,
                needs_reverify_at = CASE WHEN verification.needs_reverify = 1 THEN NULL ELSE verification.needs_reverify_at END
            """,
            (
                member.id,
                cased_handle,
                membership_status,
                int(time.time()),
                community_moniker,
            ),
        )
        await db.commit()
        logger.info(
            f"Stored verification data for user {member.display_name} ({member.id})"
        )

        try:
            await enqueue_verification_event(
                member, prev_status or "non_member", membership_status
            )
        except Exception as e:
            logger.warning(
                f"Failed to enqueue announcement event: {e}",
                extra={"user_id": member.id},
            )

            # Schedule next auto-recheck immediately after successful upsert and enqueuing announcement
        try:
            now = int(time.time())
            next_retry = _compute_next_recheck(bot, membership_status, now)
            if next_retry > 0:
                await Database.upsert_auto_recheck_success(
                    member.id, next_retry_at=next_retry, now=now, new_fail_count=0
                )
        except Exception as e:
            logger.warning(
                f"Failed to update auto recheck schedule for {member.id}: {e}"
            )

            # Identify roles to remove
    conflicting_roles = [main_role, affiliate_role, non_member_role]
    for role in conflicting_roles:
        if role and role in member.roles and role not in roles_to_add:
            roles_to_remove.append(role)
            logger.debug(f"Scheduling role for removal: {role.name}")

            # Enqueue removals
    if roles_to_remove:

        async def remove_task() -> None:
            try:
                await remove_roles(
                    member, *roles_to_remove, reason="Updating roles after verification"
                )
                removed_roles = [role.name for role in roles_to_remove]
                logger.info(
                    "Removed roles from user.",
                    extra={"user_id": member.id, "roles_removed": removed_roles},
                )
            except discord.Forbidden:
                logger.warning(
                    "Cannot remove roles due to permission hierarchy.",
                    extra={"user_id": member.id},
                )
            except Exception as e:
                logger.exception(
                    f"Failed to remove roles: {e}", extra={"user_id": member.id}
                )

        await enqueue_task(remove_task)

        # Enqueue additions
    if roles_to_add:

        async def add_task() -> None:
            nonlocal assigned_role_type

            try:
                await add_roles(
                    member, *roles_to_add, reason="Roles assigned after verification"
                )
                added_roles = [role.name for role in roles_to_add]
                logger.info(
                    "Assigned roles to user.",
                    extra={"user_id": member.id, "roles_added": added_roles},
                )
            except discord.Forbidden:
                logger.warning(
                    "Cannot assign roles due to permission hierarchy.",
                    extra={"user_id": member.id},
                )
                assigned_role_type = "unknown"
            except Exception as e:
                logger.exception(
                    f"Failed to assign roles: {e}", extra={"user_id": member.id}
                )
                assigned_role_type = "unknown"

        await enqueue_task(add_task)
    else:
        logger.error("No valid roles to add.", extra={"user_id": member.id})

        # Enqueue nickname change
    # Nickname policy (Discord nickname, not global username):
    # Updated Aug 2025: Always use the RSI handle (cased) for nickname, never the community moniker.
    # We still store the community_moniker in the DB above for future features, but it is not
    # considered for nickname selection anymore.
    preferred_nick = cased_handle

    def _truncate_nickname(nick: str, limit: int = 32) -> str:
        """Unicode-aware truncation that avoids leaving trailing combining marks.

        Python's slicing is codepoint-aware, but a slice may end with a combining mark.
        We reserve one char for an ellipsis when truncating and ensure we don't end on a combining mark.
        """
        if len(nick) <= limit:
            return nick
        import unicodedata

        base = limit - 1
        truncated = nick[:base]
        # Strip trailing combining marks
        while truncated and unicodedata.combining(truncated[-1]):
            truncated = truncated[:-1]
        return f"{truncated}…"

    if preferred_nick and can_modify_nickname(member):
        nick_final = _truncate_nickname(preferred_nick)
        # Persist preferred nick regardless of change for logging heuristics
        with contextlib.suppress(Exception):
            member._preferred_verification_nick = nick_final
        current_nick = getattr(member, "nick", None)
        if current_nick != nick_final:
            with contextlib.suppress(Exception):
                member._nickname_changed_flag = True

            async def nickname_task() -> None:
                try:
                    await edit_member(member, nick=nick_final)
                    logger.info(
                        "Nickname changed for user.",
                        extra={"user_id": member.id, "new_nickname": nick_final},
                    )
                except discord.Forbidden:
                    logger.warning(
                        "Bot lacks permission to change nickname due to role hierarchy.",
                        extra={"user_id": member.id},
                    )
                except Exception as e:
                    logger.exception(
                        f"Unexpected error when changing nickname: {e}",
                        extra={"user_id": member.id},
                    )

            await enqueue_task(nickname_task)
        else:
            with contextlib.suppress(Exception):
                member._nickname_changed_flag = False
    else:
        logger.warning(
            "Cannot change nickname due to role hierarchy.",
            extra={"user_id": member.id},
        )

        # Return old and new status
    return prev_status or "unknown", assigned_role_type


def can_modify_nickname(member: discord.Member) -> bool:
    """
    Strict nickname guard:
    - False for guild owner
    - False if bot lacks Manage Nicknames permission
    - False if bot.top_role <= member.top_role
    """
    guild = member.guild
    bot_member = guild.me

    # Cannot edit the guild owner, ever.
    if member.id == guild.owner_id:
        return False

        # Bot must have Manage Nicknames permission.
    if not bot_member.guild_permissions.manage_nicknames:
        return False

        # Bot must be higher in role hierarchy than the member.
    return bot_member.top_role > member.top_role


async def reverify_member(member: discord.Member, rsi_handle: str, bot) -> tuple:
    """Re-check a member's roles based on their RSI handle.

    Caller is responsible for catching NotFoundError (RSI 404) and invoking
    unified remediation handler.

    Args:
        member: Discord member to reverify
        rsi_handle: RSI handle to verify
        bot: Bot instance (commands.Bot or discord.Client) with http_client attribute

    Raises:
        TypeError: If bot parameter is not a proper Bot/Client instance
    """
    from helpers.http_helper import NotFoundError  # noqa: F401 (re-export for callers)
    from utils.logging import get_logger
    from verification.rsi_verification import is_valid_rsi_handle

    logger = get_logger(__name__)

    # Type validation at service boundary
    if isinstance(bot, str):
        error_msg = f"reverify_member received string '{bot}' instead of Bot instance. Check caller implementation."
        logger.error(error_msg, extra={"user_id": member.id, "rsi_handle": rsi_handle})
        raise TypeError(error_msg)

    if not hasattr(bot, "http_client") and not (
        hasattr(bot, "services") and hasattr(bot.services, "http_client")
    ):
        error_msg = f"Bot instance passed to reverify_member lacks http_client attribute. Type: {type(bot).__name__}"
        logger.error(error_msg, extra={"user_id": member.id, "rsi_handle": rsi_handle})
        raise TypeError(error_msg)

    # Get HTTP client from bot services or fallback to bot.http_client
    http_client = None
    if hasattr(bot, "services") and hasattr(bot.services, "http_client"):
        http_client = bot.services.http_client
    elif hasattr(bot, "http_client"):
        http_client = bot.http_client
    else:
        logger.error("No HTTP client found in bot services or bot object")
        return False, "error", "HTTP client unavailable for RSI verification."

    try:
        verify_value, cased_handle, community_moniker = await is_valid_rsi_handle(
            rsi_handle, http_client
        )  # May raise NotFoundError
    except Exception as e:
        logger.exception(
            "Error calling is_valid_rsi_handle for %s", rsi_handle, exc_info=e
        )
        return False, "error", f"RSI verification failed: {e!s}"

    if verify_value is None or cased_handle is None:  # moniker optional
        logger.error(
            f"is_valid_rsi_handle returned None values for {rsi_handle}: verify_value={verify_value}, cased_handle={cased_handle}"
        )
        return (
            False,
            "unknown",
            "Failed to verify RSI handle - received invalid response from RSI services.",
        )

    role_type = await assign_roles(
        member, verify_value, cased_handle, bot, community_moniker=community_moniker
    )
    return True, role_type, None
