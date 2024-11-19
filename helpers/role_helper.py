# helpers/role_helper.py

import discord
from typing import List, Optional
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

async def get_roles(member: discord.Member, role_ids: List[int]) -> List[Optional[discord.Role]]:
    """
    Retrieve roles from the guild using the member's guild.

    Args:
        member (discord.Member): The member whose guild is used to fetch roles.
        role_ids (List[int]): A list of role IDs to fetch.

    Returns:
        List[Optional[discord.Role]]: A list of roles corresponding to the provided IDs.
                                      None if a role is not found.
    """
    roles = []
    for role_id in role_ids:
        try:
            # Ensure the role_id is an integer
            role_id_int = int(role_id)
        except ValueError:
            logger.error(f"Role ID '{role_id}' is not a valid integer.")
            roles.append(None)
            continue

        logger.debug(f"Fetching role with ID: {role_id_int}")
        role = member.guild.get_role(role_id_int)
        if role:
            logger.debug(f"Role found: {role.name} (ID: {role_id_int})")
            roles.append(role)
        else:
            logger.warning(f"Role with ID {role_id_int} not found in guild '{member.guild.name}'.")
            roles.append(None)
    return roles

async def assign_roles(member: discord.Member, verify_value: int, cased_handle: str, bot) -> str:
    """
    Assigns roles to the member based on their verification status.

    Args:
        member (discord.Member): The member to assign roles to.
        verify_value (int): Verification status (1: main, 2: affiliate, 0: non-member).
        cased_handle (str): The correctly cased RSI handle of the user.
        bot (commands.Bot): The bot instance.

    Returns:
        str: The type of role assigned ('main', 'affiliate', 'non_member', or 'unknown').
    """
    role_ids = [
        bot.config['roles']['bot_verified_role_id'],
        bot.config['roles']['main_role_id'],
        bot.config['roles']['affiliate_role_id'],
        bot.config['roles']['non_member_role_id']
    ]

    # Log the role IDs being processed
    logger.debug(f"Role IDs to process: {role_ids}")
    logger.debug(f"verify_value: {verify_value}, type: {type(verify_value)}")

    # Convert role IDs to integers
    try:
        role_ids = [int(role_id) for role_id in role_ids]
    except ValueError as e:
        logger.error(f"One or more role IDs are not valid integers: {e}")
        return 'unknown'

    # Fetch roles using the updated get_roles function
    roles = await get_roles(member, role_ids)
    bot_verified_role, main_role, affiliate_role, non_member_role = roles

    # Log fetched roles
    logger.debug(f"Fetched roles: {roles}")

    # Initialize lists for roles to add and remove
    roles_to_add = []
    roles_to_remove = []
    assigned_role_type = 'unknown'

    # Always add BOT_VERIFIED_ROLE_ID if not already present
    if bot_verified_role and bot_verified_role not in member.roles:
        roles_to_add.append(bot_verified_role)
        logger.debug(f"Appending role to add: {bot_verified_role.name}")

    # Determine which specific role to assign based on verify_value
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

    # Log assigned_role_type
    logger.debug(f"Assigned role type: {assigned_role_type}")

    # Identify conflicting roles to remove
    conflicting_roles = [main_role, affiliate_role, non_member_role]
    for role in conflicting_roles:
        if role and role in member.roles and role not in roles_to_add:
            roles_to_remove.append(role)
            logger.debug(f"Scheduling role for removal: {role.name}")

    # Remove conflicting roles
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Updating roles after verification")
            removed_role_names = [role.name for role in roles_to_remove]
            logger.info("Removed roles from user.", extra={
                'user_id': member.id,
                'roles_removed': removed_role_names
            })
        except discord.Forbidden:
            logger.warning("Cannot remove roles due to permission hierarchy.", extra={'user_id': member.id})
        except Exception as e:
            logger.exception(f"Failed to remove roles: {e}", extra={'user_id': member.id})

    # Add the necessary roles
    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Roles assigned after verification")
            added_role_names = [role.name for role in roles_to_add]
            logger.info("Assigned roles to user.", extra={
                'user_id': member.id,
                'roles_added': added_role_names
            })
        except discord.Forbidden:
            logger.warning("Cannot assign roles due to permission hierarchy.", extra={'user_id': member.id})
            assigned_role_type = 'unknown'
        except Exception as e:
            logger.exception(f"Failed to assign roles: {e}", extra={'user_id': member.id})
            assigned_role_type = 'unknown'
    else:
        logger.error("No valid roles to add.", extra={'user_id': member.id})

    # Check role hierarchy before attempting to change nickname
    if can_modify_nickname(member):
        # Bot's role is higher; attempt to change nickname
        try:
            await member.edit(nick=cased_handle[:32])  # Ensure nickname length <= 32
            logger.info("Nickname changed for user.", extra={
                'user_id': member.id,
                'new_nickname': cased_handle[:32]
            })
        except discord.Forbidden:
            logger.warning("Bot lacks permission to change nickname due to role hierarchy.", extra={'user_id': member.id})
        except Exception as e:
            logger.exception(f"Unexpected error when changing nickname: {e}", extra={'user_id': member.id})
    else:
        logger.warning("Cannot change nickname due to role hierarchy.", extra={'user_id': member.id})

    return assigned_role_type

def can_modify_nickname(member: discord.Member) -> bool:
    """
    Checks if the bot can modify the member's nickname based on role hierarchy.

    Args:
        member (discord.Member): The member to check.

    Returns:
        bool: True if the bot can modify, False otherwise.
    """
    guild = member.guild
    bot_member = guild.me
    can_modify = bot_member.top_role > member.top_role
    logger.debug(f"Can modify nickname: {can_modify} (Bot Top Role: {bot_member.top_role}, Member Top Role: {member.top_role})")
    return can_modify
