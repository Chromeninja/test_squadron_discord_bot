# helpers/permissions_helper.py

import discord
from helpers.voice_utils import safe_edit_channel
from helpers.logger import get_logger
import json
import asyncio

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
        desired_state = not enable  # If PTT is enabled, disable voice activation
        if overwrite.use_voice_activation != desired_state:
            overwrite.use_voice_activation = desired_state
            overwrites[channel.guild.default_role] = overwrite
            logger.info(f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} for everyone in channel '{channel.name}'.")
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
                        logger.info(f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} for user '{member.display_name}' in channel '{channel.name}'.")
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        overwrites[role] = overwrite
                        logger.info(f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} for role '{role.name}' in channel '{channel.name}'.")
            else:
                logger.warning(f"Unknown target type: {target_type}")

    # Apply all overwrites in a single API call
    try:
        await safe_edit_channel(channel, overwrites=overwrites)
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
        desired_connect = True if action == 'permit' else False
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
                        logger.info(f"Prepared permission '{action}' for user '{member.display_name}' in channel '{channel.name}'.")
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    if overwrite.connect != desired_connect:
                        overwrite.connect = desired_connect
                        overwrites[role] = overwrite
                        logger.info(f"Prepared permission '{action}' for role '{role.name}' in channel '{channel.name}'.")
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
                        logger.info(f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} for user '{member.display_name}' in channel '{channel.name}'.")
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        overwrites[role] = overwrite
                        logger.info(f"Prepared PTT settings: {'Enabled' if enable else 'Disabled'} for role '{role.name}' in channel '{channel.name}'.")
            else:
                logger.warning(f"Unknown target type: {target_type}")

    else:
        logger.warning(f"Unknown action: {action}")
        return

    # Apply all overwrites in a single API call
    try:
        await safe_edit_channel(channel, overwrites=overwrites)
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
        await safe_edit_channel(channel, overwrites=overwrites)
        logger.info(f"Reset permissions for channel '{channel.name}' to default.")
    except Exception as e:
        logger.error(f"Failed to reset permissions for channel '{channel.name}': {e}")
        raise
