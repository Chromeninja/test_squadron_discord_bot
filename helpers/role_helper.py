# helpers/role_helper.py

import discord
import logging
from typing import List, Optional


async def get_roles(guild: discord.Guild, role_ids: List[int]) -> List[Optional[discord.Role]]:
    """
    Retrieve roles from the guild based on a list of role IDs.

    Args:
        guild (discord.Guild): The guild from which to retrieve roles.
        role_ids (List[int]): A list of role IDs to fetch.

    Returns:
        List[Optional[discord.Role]]: A list of roles corresponding to the provided IDs.
                                      None if a role is not found.
    """
    roles = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role)
        else:
            logging.warning(f"Role with ID {role_id} not found in guild '{guild.name}'.")
            roles.append(None)
    return roles


async def assign_roles(member: discord.Member, verify_value: int, rsi_handle_value: str, bot) -> str:
    """
    Assigns roles to the member based on their verification status.

    Args:
        member (discord.Member): The member to assign roles to.
        verify_value (int): Verification status (1: main, 2: affiliate, 0: non-member).
        rsi_handle_value (str): The RSI handle of the user.
        bot (commands.Bot): The bot instance.

    Returns:
        str: The type of role assigned ('main', 'affiliate', 'non_member', or 'unknown').
    """
    guild = member.guild
    role_ids = [
        bot.BOT_VERIFIED_ROLE_ID,
        bot.MAIN_ROLE_ID,
        bot.AFFILIATE_ROLE_ID,
        bot.NON_MEMBER_ROLE_ID
    ]
    roles = await get_roles(guild, role_ids)
    bot_verified_role, main_role, affiliate_role, non_member_role = roles

    # Initialize lists for roles to add and remove
    roles_to_add = []
    roles_to_remove = []
    assigned_role_type = 'unknown'

    # Always add BOT_VERIFIED_ROLE_ID if not already present
    if bot_verified_role and bot_verified_role not in member.roles:
        roles_to_add.append(bot_verified_role)

    # Determine which specific role to assign based on verify_value
    if verify_value == 1 and main_role:
        roles_to_add.append(main_role)
        assigned_role_type = 'main'
    elif verify_value == 2 and affiliate_role:
        roles_to_add.append(affiliate_role)
        assigned_role_type = 'affiliate'
    elif verify_value == 0 and non_member_role:
        roles_to_add.append(non_member_role)
        assigned_role_type = 'non_member'

    # Identify conflicting roles to remove
    conflicting_roles = [main_role, affiliate_role, non_member_role]
    for role in conflicting_roles:
        if role and role in member.roles and role not in roles_to_add:
            roles_to_remove.append(role)

    # Remove conflicting roles
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Updating roles after verification")
            removed_role_names = [role.name for role in roles_to_remove]
            logging.info(f"Removed roles: {removed_role_names} from user {member}.")
        except discord.Forbidden:
            logging.warning(f"Cannot remove roles from user {member} due to permission hierarchy.")
        except Exception as e:
            logging.exception(f"Failed to remove roles from user {member}: {e}")

    # Add the necessary roles
    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Roles assigned after verification")
            added_role_names = [role.name for role in roles_to_add]
            logging.info(f"Assigned roles: {added_role_names} to user {member}.")
        except discord.Forbidden:
            logging.warning(f"Cannot assign roles to user {member} due to permission hierarchy.")
            assigned_role_type = 'unknown'
        except Exception as e:
            logging.exception(f"Failed to assign roles to user {member}: {e}")
            assigned_role_type = 'unknown'
    else:
        logging.error("No valid roles to add.")
        assigned_role_type = 'unknown'

    # Check role hierarchy before attempting to change nickname
    if can_modify_nickname(bot, member):
        # Bot's role is higher; attempt to change nickname
        try:
            await member.edit(nick=rsi_handle_value[:32])
            logging.info(f"Nickname changed to {rsi_handle_value[:32]} for user {member}.")
        except discord.Forbidden:
            logging.warning(f"Bot lacks permission to change nickname for user {member} due to role hierarchy.")
        except Exception as e:
            logging.exception(f"Unexpected error when changing nickname for user {member}: {e}")
    else:
        logging.warning(f"Cannot change nickname for user {member} due to role hierarchy.")

    return assigned_role_type


def can_modify_nickname(bot, member) -> bool:
    """
    Checks if the bot can modify the member's nickname based on role hierarchy.

    Args:
        bot (commands.Bot): The bot instance.
        member (discord.Member): The member to check.

    Returns:
        bool: True if the bot can modify, False otherwise.
    """
    guild = member.guild
    bot_member = guild.me
    return bot_member.top_role > member.top_role
