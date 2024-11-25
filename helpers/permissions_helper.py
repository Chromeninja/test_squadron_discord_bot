# helpers/permissions_helper.py

import discord
from helpers.logger import get_logger
import json

logger = get_logger(__name__)


async def apply_ptt_settings(channel: discord.VoiceChannel, ptt_settings: dict):
    """
    Applies PTT settings to the channel based on the provided configuration.

    Args:
        channel (discord.VoiceChannel): The voice channel to modify.
        ptt_settings (dict): The PTT settings.
    """
    target = ptt_settings.get('target', 'everyone')
    enable = ptt_settings.get('enabled', True)

    if target == 'everyone':
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.use_voice_activation = not enable
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)
    elif target == 'role':
        role_id = ptt_settings.get('role_id')
        if role_id:
            role = channel.guild.get_role(role_id)
            if role:
                overwrite = channel.overwrites_for(role)
                overwrite.use_voice_activation = not enable
                await channel.set_permissions(role, overwrite=overwrite)
    elif target == 'user':
        user_id = ptt_settings.get('user_id')
        if user_id:
            user = channel.guild.get_member(user_id)
            if user:
                overwrite = channel.overwrites_for(user)
                overwrite.use_voice_activation = not enable
                await channel.set_permissions(user, overwrite=overwrite)

    logger.info(f"Applied PTT settings: {'Enabled' if enable else 'Disabled'} for {target} in channel '{channel.name}'.")


async def apply_permissions_changes(channel: discord.VoiceChannel, perm_settings: dict):
    """
    Applies permissions changes to the channel based on the provided configuration.

    Args:
        channel (discord.VoiceChannel): The voice channel to modify.
        perm_settings (dict): The permissions settings.
    """
    action = perm_settings.get('action')
    targets = perm_settings.get('targets', [])
    enable = permission_change.get('enable', None)
    for target in targets:
        target_type = target.get('type')  # 'user' or 'role'
        target_id = target.get('id')
        for target in targets:
            if target['type'] == 'user':
                member = channel.guild.get_member(target['id'])
                if member:
                    overwrite = channel.overwrites_for(member)
                    if action == 'permit':
                        overwrite.connect = True
                    elif action == 'reject':
                        overwrite.connect = False
                        if member in channel.members:
                            await member.move_to(None)
                    elif action == 'ptt':
                        if enable is not None:
                            overwrite.use_voice_activation = not enable
                    await channel.set_permissions(member, overwrite=overwrite)
            elif target['type'] == 'role':
                role = channel.guild.get_role(target['id'])
                if role:
                    overwrite = channel.overwrites_for(role)
                    if action == 'permit':
                        overwrite.connect = True
                    elif action == 'reject':
                        overwrite.connect = False
                        for member in channel.members:
                            if role in member.roles:
                                await member.move_to(None)
                    elif action == 'ptt':
                        if enable is not None:
                            overwrite.use_voice_activation = not enable
                    await channel.set_permissions(role, overwrite=overwrite)

async def reset_channel_permissions(channel: discord.VoiceChannel):
    """
    Resets the channel's permissions to default.

    Args:
        channel (discord.VoiceChannel): The voice channel to reset.
    """
    guild = channel.guild
    default_role = guild.default_role

    overwrite = channel.overwrites_for(default_role)
    overwrite.connect = True
    overwrite.use_voice_activation = True
    overwrite.manage_channels = False
    await channel.set_permissions(default_role, overwrite=overwrite)

    # Remove all other overwrites except for the owner and the bot
    for target, perms in channel.overwrites.items():
        if isinstance(target, discord.Role) and target != default_role:
            await channel.set_permissions(target, overwrite=None)
        elif isinstance(target, discord.Member) and target != channel.guild.me:
            await channel.set_permissions(target, overwrite=None)

    logger.info(f"Reset permissions for channel '{channel.name}' to default.")
