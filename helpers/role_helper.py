import contextlib
import json
import random
import time

import discord

from helpers.discord_api import add_roles, edit_member, remove_roles
from helpers.task_queue import enqueue_task
from services.db.database import Database, get_cross_guild_membership_status
from utils.logging import get_logger

logger = get_logger(__name__)


async def _compute_next_recheck(bot, user_id: int, now: int) -> int:
    """
    Compute next auto-recheck timestamp based on user's cross-guild membership status.

    Uses the highest membership status across ALL guilds tracking user's organizations:
    - Main member of ANY tracked org: 14 days
    - Affiliate only across all tracked orgs: 7 days
    - Non-member: 3 days

    Args:
        bot: Bot instance with config
        user_id: Discord user ID
        now: Current timestamp

    Returns:
        Unix timestamp for next recheck, or 0 if auto-recheck disabled
    """
    cfg = (bot.config or {}).get("auto_recheck", {}) or {}
    cadence_map = cfg.get("cadence_days") or {}
    jitter_h = int(cfg.get("jitter_hours") or 0)

    # Get cross-guild membership status
    status = await get_cross_guild_membership_status(user_id)

    days = int(cadence_map.get(status or "", 0))  # Default 0 -> skip if unknown
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
    main_orgs: list[str] | None = None,
    affiliate_orgs: list[str] | None = None,
) -> None:
    """Assign roles based on verification status.

    Args:
        member: Discord member to assign roles to
        verify_value: Verification status (0, 1, 2)
        cased_handle: Properly cased RSI handle
        bot: Bot instance with role_cache and other attributes
        community_moniker: Optional community moniker
        main_orgs: List of main organization SIDs
        affiliate_orgs: List of affiliate organization SIDs

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

    # Fetch previous org lists before DB update for announcement comparison
    prev_main_orgs = None
    prev_affiliate_orgs = None
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT main_orgs, affiliate_orgs FROM verification WHERE user_id = ?",
            (member.id,),
        )
        row = await cursor.fetchone()
        if row:
            prev_main_orgs_json, prev_affiliate_orgs_json = row
            if prev_main_orgs_json:
                prev_main_orgs = json.loads(prev_main_orgs_json)
            if prev_affiliate_orgs_json:
                prev_affiliate_orgs = json.loads(prev_affiliate_orgs_json)

    # Get role configuration from database for this guild
    if hasattr(bot, "services") and bot.services:
        try:
            # Fetch role IDs from database (stored as lists, use first item)
            main_role_ids = await bot.services.config.get_guild_setting(
                member.guild.id, "roles.main_role", []
            )
            affiliate_role_ids = await bot.services.config.get_guild_setting(
                member.guild.id, "roles.affiliate_role", []
            )
            nonmember_role_ids = await bot.services.config.get_guild_setting(
                member.guild.id, "roles.nonmember_role", []
            )

            # Get first role ID from each list
            main_role_id = main_role_ids[0] if main_role_ids else None
            affiliate_role_id = affiliate_role_ids[0] if affiliate_role_ids else None
            non_member_role_id = nonmember_role_ids[0] if nonmember_role_ids else None

            # Get role objects from cache or guild
            main_role = bot.role_cache.get(main_role_id) if main_role_id else None
            affiliate_role = (
                bot.role_cache.get(affiliate_role_id) if affiliate_role_id else None
            )
            non_member_role = (
                bot.role_cache.get(non_member_role_id) if non_member_role_id else None
            )
        except Exception as e:
            logger.exception(f"Error fetching role configuration from database: {e}")
            main_role = affiliate_role = non_member_role = None
    else:
        logger.warning("Bot services not available, cannot fetch role configuration")
        main_role = affiliate_role = non_member_role = None

    # Note: bot_verified_role handling removed - no longer used
    roles_to_add = []
    roles_to_remove = []
    assigned_role_type = "unknown"

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

    # Update DB - remove membership_status column, rely on org lists
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT INTO verification (user_id, rsi_handle, last_updated, community_moniker, main_orgs, affiliate_orgs)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                rsi_handle = excluded.rsi_handle,
                last_updated = excluded.last_updated,
                community_moniker = excluded.community_moniker,
                main_orgs = excluded.main_orgs,
                affiliate_orgs = excluded.affiliate_orgs,
                -- Only clear needs_reverify if it was previously set (successful re-verification)
                needs_reverify = CASE WHEN verification.needs_reverify = 1 THEN 0 ELSE verification.needs_reverify END,
                needs_reverify_at = CASE WHEN verification.needs_reverify = 1 THEN NULL ELSE verification.needs_reverify_at END
            """,
            (
                member.id,
                cased_handle,
                int(time.time()),
                community_moniker,
                json.dumps(main_orgs) if main_orgs else None,
                json.dumps(affiliate_orgs) if affiliate_orgs else None,
            ),
        )
        await db.commit()
        logger.info(
            f"Stored verification data for user {member.display_name} ({member.id})"
        )

        # Always enqueue announcement check - guild-aware function handles status derivation
        from helpers.announcement import enqueue_announcement_for_guild

        try:
            await enqueue_announcement_for_guild(
                bot,
                member,
                main_orgs,
                affiliate_orgs,
                prev_main_orgs,
                prev_affiliate_orgs,
            )
        except Exception as e:
            logger.warning(
                f"Failed to enqueue guild-aware announcement: {e}",
                extra={"user_id": member.id},
            )

            # Schedule next auto-recheck immediately after successful upsert and enqueuing announcement
        try:
            now = int(time.time())
            next_retry = await _compute_next_recheck(bot, member.id, now)
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
    # Nickname policy: Always use RSI handle (properly cased) as Discord nickname.
    # Community moniker is stored in DB but not used for nickname display.
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

        # Return old and new status in database format (derived from org lists)
    from services.db.database import derive_membership_status

    # Get guild org SID for status derivation
    guild_org_sid = "TEST"
    if (
        hasattr(bot, "services")
        and bot.services
        and hasattr(bot.services, "guild_config")
    ):
        try:
            guild_org_sid = await bot.services.guild_config.get_setting(
                member.guild.id, "organization.sid", default="TEST"
            )
            if isinstance(guild_org_sid, str) and guild_org_sid.startswith('"'):
                guild_org_sid = guild_org_sid.strip('"')
        except Exception:
            pass

    prev_status_derived = derive_membership_status(
        prev_main_orgs, prev_affiliate_orgs, guild_org_sid
    )
    new_status_derived = derive_membership_status(
        main_orgs, affiliate_orgs, guild_org_sid
    )

    return prev_status_derived, new_status_derived


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

    # Get organization config from guild
    org_name = "test"  # Default fallback
    org_sid = None
    if hasattr(bot, "services") and hasattr(bot.services, "guild_config"):
        try:
            org_name_config = await bot.services.guild_config.get_setting(
                member.guild.id, "organization.name", default="test"
            )
            org_name = org_name_config.strip().lower() if org_name_config else "test"

            org_sid_config = await bot.services.guild_config.get_setting(
                member.guild.id, "organization.sid", default=None
            )
            org_sid = org_sid_config.strip().upper() if org_sid_config else None
        except Exception as e:
            logger.warning(
                f"Failed to get org config, using defaults: {e}",
                extra={"guild_id": member.guild.id},
            )

    try:
        (
            verify_value,
            cased_handle,
            community_moniker,
            main_orgs,
            affiliate_orgs,
        ) = await is_valid_rsi_handle(
            rsi_handle, http_client, org_name, org_sid
        )  # May raise NotFoundError
    except Exception as e:
        logger.exception(
            "Error calling is_valid_rsi_handle for %s", rsi_handle, exc_info=e
        )
        return False, "error", f"Unexpected error: {e}"

    if verify_value is None or cased_handle is None:
        logger.error(
            f"is_valid_rsi_handle returned None values for {rsi_handle}: verify_value={verify_value}, cased_handle={cased_handle}"
        )
        return (
            False,
            "unknown",
            "Failed to verify RSI handle - received invalid response from RSI services.",
        )

    role_type = await assign_roles(
        member,
        verify_value,
        cased_handle,
        bot,
        community_moniker=community_moniker,
        main_orgs=main_orgs,
        affiliate_orgs=affiliate_orgs,
    )
    return True, role_type, None
