# helpers/permissions_helper.py

import discord
from helpers.logger import get_logger
import asyncio

logger = get_logger(__name__)

async def apply_ptt_settings(channel: discord.VoiceChannel, ptt_settings: dict):
    """
    Applies PTT settings to the channel based on the provided configuration.

    Args:
        channel (discord.VoiceChannel): The voice channel to modify.
        ptt_settings (dict): The PTT settings.
    """
    enable = ptt_settings.get('enable', True)
    targets = ptt_settings.get('targets', [])

    if not targets:
        # Apply to @everyone
        overwrite = channel.overwrites_for(channel.guild.default_role)
        if overwrite.use_voice_activation != (not enable):
            overwrite.use_voice_activation = not enable
            await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)
            logger.info(f"Applied PTT settings: {'Enabled' if enable else 'Disabled'} for everyone in channel '{channel.name}'.")
            await asyncio.sleep(1)  # Delay to prevent rate limits
    else:
        for target in targets:
            if target['type'] == 'user':
                member = channel.guild.get_member(target['id'])
                if member:
                    overwrite = channel.overwrites_for(member)
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        await channel.set_permissions(member, overwrite=overwrite)
                        logger.info(f"Applied PTT settings: {'Enabled' if enable else 'Disabled'} for user '{member.display_name}' in channel '{channel.name}'.")
                        await asyncio.sleep(1)  # Delay to prevent rate limits
            elif target['type'] == 'role':
                role = channel.guild.get_role(target['id'])
                if role:
                    overwrite = channel.overwrites_for(role)
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        await channel.set_permissions(role, overwrite=overwrite)
                        logger.info(f"Applied PTT settings: {'Enabled' if enable else 'Disabled'} for role '{role.name}' in channel '{channel.name}'.")
                        await asyncio.sleep(1)  # Delay to prevent rate limits

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

    for target in targets:
        target_type = target.get('type')  # 'user' or 'role'
        target_id = target.get('id')
        if target_type == 'user':
            member = channel.guild.get_member(target_id)
            if member:
                overwrite = channel.overwrites_for(member)
                changed = False
                if action == 'permit':
                    if overwrite.connect != True:
                        overwrite.connect = True
                        changed = True
                elif action == 'reject':
                    if overwrite.connect != False:
                        overwrite.connect = False
                        changed = True
                        if member in channel.members:
                            try:
                                await member.move_to(None)
                                logger.info(f"Moved user '{member.display_name}' out of channel '{channel.name}' due to rejection.")
                            except Exception as e:
                                logger.error(f"Failed to move user '{member.display_name}': {e}")
                elif action == 'ptt' and enable is not None:
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        changed = True
                if changed:
                    await channel.set_permissions(member, overwrite=overwrite)
                    logger.info(f"Applied permission '{action}' to user '{member.display_name}' in channel '{channel.name}'.")
                    await asyncio.sleep(1)  # Delay to prevent rate limits
        elif target_type == 'role':
            role = channel.guild.get_role(target_id)
            if role:
                overwrite = channel.overwrites_for(role)
                changed = False
                if action == 'permit':
                    if overwrite.connect != True:
                        overwrite.connect = True
                        changed = True
                elif action == 'reject':
                    if overwrite.connect != False:
                        overwrite.connect = False
                        changed = True
                        # Move all members with this role out of the channel
                        for member in channel.members:
                            if role in member.roles:
                                try:
                                    await member.move_to(None)
                                    logger.info(f"Moved user '{member.display_name}' out of channel '{channel.name}' due to role rejection.")
                                except Exception as e:
                                    logger.error(f"Failed to move user '{member.display_name}': {e}")
                elif action == 'ptt' and enable is not None:
                    desired_state = not enable
                    if overwrite.use_voice_activation != desired_state:
                        overwrite.use_voice_activation = desired_state
                        changed = True
                if changed:
                    await channel.set_permissions(role, overwrite=overwrite)
                    logger.info(f"Applied permission '{action}' to role '{role.name}' in channel '{channel.name}'.")
                    await asyncio.sleep(1)  # Delay to prevent rate limits

async def reset_channel_permissions(channel: discord.VoiceChannel):
    """
    Resets the channel's permissions to default.

    Args:
        channel (discord.VoiceChannel): The voice channel to reset.
    """
    guild = channel.guild
    default_role = guild.default_role

    # Reset permissions for @everyone
    overwrite = discord.PermissionOverwrite()
    overwrite.connect = True
    overwrite.use_voice_activation = True
    await channel.set_permissions(default_role, overwrite=overwrite)
    logger.info(f"Reset permissions for @everyone in channel '{channel.name}'.")
    await asyncio.sleep(1)  # Delay to prevent rate limits

    # Remove all other overwrites except for the owner and the bot
    for target, perms in list(channel.overwrites.items()):
        if isinstance(target, discord.Member) and target != guild.me:
            await channel.set_permissions(target, overwrite=None)
            logger.info(f"Removed permissions for user '{target.display_name}' in channel '{channel.name}'.")
            await asyncio.sleep(1)  # Delay to prevent rate limits
        elif isinstance(target, discord.Role) and target != default_role:
            await channel.set_permissions(target, overwrite=None)
            logger.info(f"Removed permissions for role '{target.name}' in channel '{channel.name}'.")
            await asyncio.sleep(1)  # Delay to prevent rate limits

    logger.info(f"All non-default permissions reset for channel '{channel.name}'.")
