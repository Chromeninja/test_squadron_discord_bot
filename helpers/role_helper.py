"""
Role helper module for applying roles and nicknames based on verification status.

This module provides the core role application logic used by the unified
verification pipeline. It handles role assignment/removal and nickname
changes based on a user's verification status.

For full verification flow, use the unified pipeline:
    - services.verification_state.compute_global_state()
    - services.verification_state.store_global_state()
    - services.guild_sync.apply_state_to_guild()
    - helpers.verification_logging.log_guild_sync()
    - services.verification_scheduler.schedule_user_recheck()
"""

import discord

from helpers.discord_api import add_roles, edit_member, remove_roles
from helpers.task_queue import enqueue_task
from services.db.database import Database
from utils.logging import get_logger

__all__ = ["apply_roles_for_status", "can_modify_nickname"]

logger = get_logger(__name__)


async def apply_roles_for_status(
    member: discord.Member,
    status: str,
    rsi_handle: str,
    bot,
    *,
    community_moniker: str | None = None,
    main_orgs: list[str] | None = None,
    affiliate_orgs: list[str] | None = None,
) -> tuple[str, str]:
    """Apply roles/nickname for a derived status without DB side effects."""

    if isinstance(bot, str):
        raise TypeError("apply_roles_for_status expects a bot instance, not string")

    # Fetch role configuration
    bot_verified_role = main_role = affiliate_role = non_member_role = None
    if hasattr(bot, "services") and bot.services:
        try:
            cfg = bot.services.config
            bot_verified_role_ids = await cfg.get_guild_setting(
                member.guild.id, "roles.bot_verified_role", []
            )
            main_role_ids = await cfg.get_guild_setting(
                member.guild.id, "roles.main_role", []
            )
            affiliate_role_ids = await cfg.get_guild_setting(
                member.guild.id, "roles.affiliate_role", []
            )
            nonmember_role_ids = await cfg.get_guild_setting(
                member.guild.id, "roles.nonmember_role", []
            )

            bot_verified_role = bot.role_cache.get(bot_verified_role_ids[0]) if bot_verified_role_ids else None
            main_role = bot.role_cache.get(main_role_ids[0]) if main_role_ids else None
            affiliate_role = bot.role_cache.get(affiliate_role_ids[0]) if affiliate_role_ids else None
            non_member_role = bot.role_cache.get(nonmember_role_ids[0]) if nonmember_role_ids else None
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to load role configuration: %s", e)

    verify_value_map = {"main": 1, "affiliate": 2, "non_member": 0}
    verify_value = verify_value_map.get(status, 0)

    roles_to_add = []
    if bot_verified_role:
        roles_to_add.append(bot_verified_role)
    if verify_value == 1 and main_role:
        roles_to_add.append(main_role)
    if verify_value == 2 and affiliate_role:
        roles_to_add.append(affiliate_role)
    if verify_value == 0 and non_member_role:
        roles_to_add.append(non_member_role)

    # Track membership for cleanup logic
    await Database.track_user_guild_membership(member.id, member.guild.id)

    # Identify roles to remove (managed roles not in target set)
    managed_roles = [r for r in [main_role, affiliate_role, non_member_role] if r]
    current_roles = set(member.roles)
    target_roles = {r for r in roles_to_add if r}
    roles_to_remove = [r for r in managed_roles if r in current_roles and r not in target_roles]

    # Skip no-op
    if not roles_to_add and not roles_to_remove and getattr(member, "nick", None) == rsi_handle:
        return status, status

    if roles_to_remove:

        async def remove_task() -> None:
            try:
                await remove_roles(
                    member, *roles_to_remove, reason="Updating roles after verification"
                )
            except discord.Forbidden:
                logger.warning(
                    "Cannot remove roles due to permission hierarchy.",
                    extra={"user_id": member.id},
                )
            except Exception as e:
                logger.exception("Failed to remove roles: %s", e)

        await enqueue_task(remove_task)

    if roles_to_add:

        async def add_task() -> None:
            try:
                await add_roles(member, *roles_to_add, reason="Roles assigned after verification")
            except discord.Forbidden:
                logger.warning(
                    "Cannot assign roles due to permission hierarchy.",
                    extra={"user_id": member.id},
                )
            except Exception as e:
                logger.exception("Failed to assign roles: %s", e)

        await enqueue_task(add_task)

    preferred_nick = rsi_handle

    def _truncate_nickname(nick: str, limit: int = 32) -> str:
        if len(nick) <= limit:
            return nick
        import unicodedata

        base = limit - 1
        truncated = nick[:base]
        while truncated and unicodedata.combining(truncated[-1]):
            truncated = truncated[:-1]
        return f"{truncated}…"

    if preferred_nick and can_modify_nickname(member):
        nick_final = _truncate_nickname(preferred_nick)
        current_nick = getattr(member, "nick", None)
        if current_nick != nick_final:

            async def nickname_task() -> None:
                try:
                    await edit_member(member, nick=nick_final)
                except discord.Forbidden:
                    logger.warning(
                        "Bot lacks permission to change nickname due to role hierarchy.",
                        extra={"user_id": member.id},
                    )
                except Exception as e:
                    logger.exception("Unexpected error when changing nickname: %s", e)

            await enqueue_task(nickname_task)

    return status, status


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
