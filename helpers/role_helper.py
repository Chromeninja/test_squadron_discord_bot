# helpers/role_helper.py

import time
from helpers.database import Database
import discord
from helpers.logger import get_logger

logger = get_logger(__name__)

async def assign_roles(member: discord.Member, verify_value: int, cased_handle: str, bot) -> str:
    bot_verified_role = bot.role_cache.get(bot.BOT_VERIFIED_ROLE_ID)
    main_role = bot.role_cache.get(bot.MAIN_ROLE_ID)
    affiliate_role = bot.role_cache.get(bot.AFFILIATE_ROLE_ID)
    non_member_role = bot.role_cache.get(bot.NON_MEMBER_ROLE_ID)

    roles_to_add = []
    roles_to_remove = []
    assigned_role_type = 'unknown'

    if bot_verified_role and bot_verified_role not in member.roles:
        roles_to_add.append(bot_verified_role)
        logger.debug(f"Appending role to add: {bot_verified_role.name}")

    if verify_value == 1 and main_role:
        roles_to_add.append(main_role)
        assigned_role_type = 'main'
        logger.debug(f"Appending role to add: {main_role.name}")
    elif verify_value == 2 and affiliate_role:
        roles_to_add.append(affiliate_role)
        assigned_role_type = 'affiliate'
        logger.debug(f"Appending role to add: {affiliate_role.name}")
    elif verify_value == 0 and non_member_role:
        roles_to_add.append(non_member_role)
        assigned_role_type = 'non_member'
        logger.debug(f"Appending role to add: {non_member_role.name}")
    
    # Map verify_value to membership status
    membership_status_map = {
        1: 'main',
        2: 'affiliate',
        0: 'non_member',
    }
    membership_status = membership_status_map.get(verify_value, 'unknown')

    # Use the correct method to get a database connection
    async with Database.get_connection() as db:
        await db.execute("""
            INSERT INTO verification (user_id, rsi_handle, membership_status, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                rsi_handle = excluded.rsi_handle,
                membership_status = excluded.membership_status,
                last_updated = excluded.last_updated
        """, (member.id, cased_handle, membership_status, int(time.time())))
        await db.commit()
        logger.info(f"Stored verification data for user {member.display_name} ({member.id})")

    conflicting_roles = [main_role, affiliate_role, non_member_role]
    for role in conflicting_roles:
        if role and role in member.roles and role not in roles_to_add:
            roles_to_remove.append(role)
            logger.debug(f"Scheduling role for removal: {role.name}")

    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Updating roles after verification")
            removed_roles = [role.name for role in roles_to_remove]
            logger.info("Removed roles from user.", extra={'user_id': member.id, 'roles_removed': removed_roles})
        except discord.Forbidden:
            logger.warning("Cannot remove roles due to permission hierarchy.", extra={'user_id': member.id})
        except Exception as e:
            logger.exception(f"Failed to remove roles: {e}", extra={'user_id': member.id})

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Roles assigned after verification")
            added_roles = [role.name for role in roles_to_add]
            logger.info("Assigned roles to user.", extra={'user_id': member.id, 'roles_added': added_roles})
        except discord.Forbidden:
            logger.warning("Cannot assign roles due to permission hierarchy.", extra={'user_id': member.id})
            assigned_role_type = 'unknown'
        except Exception as e:
            logger.exception(f"Failed to assign roles: {e}", extra={'user_id': member.id})
            assigned_role_type = 'unknown'
    else:
        logger.error("No valid roles to add.", extra={'user_id': member.id})

    if can_modify_nickname(member):
        try:
            await member.edit(nick=cased_handle[:32])
            logger.info("Nickname changed for user.", extra={'user_id': member.id, 'new_nickname': cased_handle[:32]})
        except discord.Forbidden:
            logger.warning("Bot lacks permission to change nickname due to role hierarchy.", extra={'user_id': member.id})
        except Exception as e:
            logger.exception(f"Unexpected error when changing nickname: {e}", extra={'user_id': member.id})
    else:
        logger.warning("Cannot change nickname due to role hierarchy.", extra={'user_id': member.id})

    return assigned_role_type
    

def can_modify_nickname(member: discord.Member) -> bool:
    guild = member.guild
    bot_member = guild.me
    can_modify = bot_member.top_role > member.top_role
    logger.debug(f"Can modify nickname: {can_modify} (Bot Top Role: {bot_member.top_role}, Member Top Role: {member.top_role})")
    return can_modify
