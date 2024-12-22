# helpers/permissions_helper.py

import discord
from helpers.database import Database
from helpers.logger import get_logger
# Import centralized API call
from helpers.discord_api import edit_channel

logger = get_logger(__name__)

async def apply_ptt_settings(channel: discord.VoiceChannel, ptt_settings: dict):
    """
    Applies PTT (Push-To-Talk) settings to the channel based on the provided configuration.

    Args:
        channel (discord.VoiceChannel): The voice channel to modify.
        ptt_settings (dict): The PTT settings.
    """
    enable = ptt_settings.get('enable', True)
    targets = ptt_settings.get('targets', [])

    # Prepare a dictionary to hold all overwrites
    overwrites = channel.overwrites.copy()

    if not targets:
        # Apply to @everyone
        overwrite = overwrites.get(channel.guild.default_role, discord.PermissionOverwrite())
        desired_state = not enable
        if overwrite.use_voice_activation != desired_state:
            overwrite.use_voice_activation = desired_state
            overwrites[channel.guild.default_role] = overwrite
            logger.info(
                f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} for everyone in channel '{channel.name}'."
            )
    else:
        for target in targets:
            target_type = target.get('type')
            target_id = target.get('id')

            if target_type == 'user':
                member = channel.guild.get_member(target_id)
                if member:
                    overwrite = overwrites.get(member, discord.PermissionOverwrite())
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        overwrites[member] = overwrite
                        logger.info(
                            f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} "
                            f"for user '{member.display_name}' in channel '{channel.name}'."
                        )
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        overwrites[role] = overwrite
                        logger.info(
                            f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} "
                            f"for role '{role.name}' in channel '{channel.name}'."
                        )
            else:
                logger.warning(f"Unknown target type: {target_type}")

    # Apply all overwrites in a single API call
    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Applied PTT settings to channel '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to apply PTT settings to channel '{channel.name}': {e}")
        raise

async def apply_permissions_changes(channel: discord.VoiceChannel, perm_settings: dict):
    """
    Applies permissions changes to the channel based on the provided configuration.

    Args:
        channel (discord.VoiceChannel): The voice channel to modify.
        perm_settings (dict): The permissions settings.
    """
    action = perm_settings.get('action')
    targets = perm_settings.get('targets', [])
    enable = perm_settings.get('enable', None)

    # Prepare a dictionary to hold all overwrites
    overwrites = channel.overwrites.copy()

    if action in ['permit', 'reject']:
        desired_connect = (action == 'permit')
        for target in targets:
            target_type = target.get('type')
            target_id = target.get('id')

            if target_type == 'user':
                member = channel.guild.get_member(target_id)
                if member:
                    overwrite = overwrites.get(member, discord.PermissionOverwrite())
                    if overwrite.connect != desired_connect:
                        overwrite.connect = desired_connect
                        overwrites[member] = overwrite
                        logger.info(
                            f"Prepared permission '{action}' for user '{member.display_name}' "
                            f"in channel '{channel.name}'."
                        )
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    if overwrite.connect != desired_connect:
                        overwrite.connect = desired_connect
                        overwrites[role] = overwrite
                        logger.info(
                            f"Prepared permission '{action}' for role '{role.name}' in channel '{channel.name}'."
                        )
            else:
                logger.warning(f"Unknown target type: {target_type}")

    elif action == 'ptt':
        for target in targets:
            target_type = target.get('type')
            target_id = target.get('id')

            if target_type == 'user':
                member = channel.guild.get_member(target_id)
                if member:
                    overwrite = overwrites.get(member, discord.PermissionOverwrite())
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        overwrites[member] = overwrite
                        logger.info(
                            f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} "
                            f"for user '{member.display_name}' in channel '{channel.name}'."
                        )
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        overwrites[role] = overwrite
                        logger.info(
                            f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} "
                            f"for role '{role.name}' in channel '{channel.name}'."
                        )
            else:
                logger.warning(f"Unknown target type: {target_type}")

    elif action in ['lock', 'unlock']:
        desired_connect = (action != 'lock')
        for target in targets:
            target_type = target.get('type')
            target_id = target.get('id')
            if target_type == 'user':
                member = channel.guild.get_member(target_id)
                if member:
                    overwrite = overwrites.get(member, discord.PermissionOverwrite())
                    overwrite.connect = desired_connect
                    overwrites[member] = overwrite
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    overwrite.connect = desired_connect
                    overwrites[role] = overwrite
            else:
                logger.warning(f"Unknown target type: {target_type}")

    else:
        logger.warning(f"Unknown action: {action}")
        return

    # Before applying overwrites, ensure owner's permissions are preserved
    try:
        # Fetch owner_id from the database
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?", (channel.id,)
            )
            row = await cursor.fetchone()
            if row:
                owner_id = row[0]
                owner = channel.guild.get_member(owner_id)
                if owner:
                    overwrite = overwrites.get(owner, discord.PermissionOverwrite())
                    overwrite.manage_channels = True
                    overwrite.connect = True
                    overwrites[owner] = overwrite
    except Exception as e:
        logger.error(f"Failed to retrieve or set owner permissions: {e}")
        # Proceeding without setting owner permissions might cause issues

    # Apply all overwrites in a single API call
    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Applied permission '{action}' to channel '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to apply permission '{action}' to channel '{channel.name}': {e}")
        raise

async def reset_channel_permissions(channel: discord.VoiceChannel):
    """
    Resets the channel's permissions to default.

    Args:
        channel (discord.VoiceChannel): The voice channel to reset.
    """
    guild = channel.guild
    default_role = guild.default_role

    # Prepare default overwrites
    overwrites = {
        default_role: discord.PermissionOverwrite(connect=True, use_voice_activation=True),
        guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True)
    }

    # Apply the default overwrites
    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Reset permissions for channel '{channel.name}' to default.")
    except Exception as e:
        logger.error(f"Failed to reset permissions for channel '{channel.name}': {e}")
        raise
    
async def update_channel_owner(channel: discord.VoiceChannel, new_owner_id: int, previous_owner_id: int):
    """
    Updates the channel owner and adjusts permissions accordingly.

    Args:
        channel (discord.VoiceChannel): The voice channel to update.
        new_owner_id (int): The user ID of the new owner.
        previous_owner_id (int): The user ID of the previous owner.
    """
    overwrites = channel.overwrites

    # Remove manage_channels permission from the previous owner
    previous_owner = channel.guild.get_member(previous_owner_id)
    if previous_owner:
        overwrites.pop(previous_owner, None)

    # Grant manage_channels permission to the new owner
    new_owner = channel.guild.get_member(new_owner_id)
    if new_owner:
        overwrites[new_owner] = discord.PermissionOverwrite(manage_channels=True, connect=True)

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Updated channel owner to '{new_owner.display_name}' for channel '{channel.name}'.")
    except Exception as e:
        logger.exception(f"Failed to update channel permissions for '{channel.name}': {e}")
        raise