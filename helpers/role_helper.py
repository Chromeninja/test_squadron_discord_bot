# helpers/role_helper.py

import discord
import logging
from typing import List, Optional

async def get_roles(guild: discord.Guild, role_ids: List[int]) -> List[Optional[discord.Role]]:
    """Retrieve roles from the guild based on a list of role IDs."""
    roles = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role)
        else:
            logging.warning(f"Role with ID {role_id} not found in guild '{guild.name}'.")
            roles.append(None)
    return roles
