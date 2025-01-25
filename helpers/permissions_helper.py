# helpers/permissions_helper.py

import discord
from helpers.database import Database
from helpers.logger import get_logger
from helpers.discord_api import edit_channel

logger = get_logger(__name__)

FEATURE_CONFIG = {
    "ptt": {
        "overwrite_property": "use_voice_activation",
        "db_table": "channel_ptt_settings",
        "db_column": "ptt_enabled",
        "inverted": True
    },
    "priority_speaker": {
        "overwrite_property": "priority_speaker",
        "db_table": "channel_priority_speaker_settings",
        "db_column": "priority_enabled",
        "inverted": False
    },
    "soundboard": {
        "overwrite_property": "use_soundboard",
        "db_table": "channel_soundboard_settings",
        "db_column": "soundboard_enabled",
        "inverted": False
    },
}

async def apply_permissions_changes(channel: discord.VoiceChannel, perm_settings: dict):
    """
    Applies basic permission changes like 'permit' or 'reject' or 'lock' or 'unlock'.
    Does NOT handle feature toggles (PTT, priority, soundboard).
    """
    action = perm_settings.get('action')
    targets = perm_settings.get('targets', [])

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
                    overwrite.connect = desired_connect
                    overwrites[member] = overwrite
            elif target_type == 'role':
                role = channel.guild.get_role(target_id)
                if role:
                    overwrite = overwrites.get(role, discord.PermissionOverwrite())
                    overwrite.connect = desired_connect
                    overwrites[role] = overwrite
            elif target_type == 'everyone':
                overwrite = overwrites.get(channel.guild.default_role, discord.PermissionOverwrite())
                overwrite.connect = desired_connect
                overwrites[channel.guild.default_role] = overwrite

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
            elif target_type == 'everyone':
                overwrite = overwrites.get(channel.guild.default_role, discord.PermissionOverwrite())
                overwrite.connect = desired_connect
                overwrites[channel.guild.default_role] = overwrite
    else:
        logger.warning(f"Unknown action: {action}")
        return

    # Ensure the owner can still manage the channel
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel.id,)
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
        logger.error(f"Failed to set owner permissions: {e}")

    # Apply overwrites
    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Applied permission '{action}' to channel '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to apply permission '{action}' to channel '{channel.name}': {e}")
        raise

async def reset_channel_permissions(channel: discord.VoiceChannel):
    """
    Resets the channel's permissions to default.
    """
    guild = channel.guild
    default_role = guild.default_role

    overwrites = {
        default_role: discord.PermissionOverwrite(connect=True, use_voice_activation=True),
        guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True)
    }

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Reset permissions for channel '{channel.name}' to default.")
    except Exception as e:
        logger.error(f"Failed to reset permissions for channel '{channel.name}': {e}")
        raise

async def update_channel_owner(channel: discord.VoiceChannel, new_owner_id: int, previous_owner_id: int):
    """
    Updates the channel owner and adjusts permissions accordingly.
    """
    overwrites = channel.overwrites.copy()

    previous_owner = channel.guild.get_member(previous_owner_id)
    if previous_owner:
        overwrites.pop(previous_owner, None)

    new_owner = channel.guild.get_member(new_owner_id)
    if new_owner:
        overwrites[new_owner] = discord.PermissionOverwrite(manage_channels=True, connect=True)

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Updated channel owner to '{new_owner.display_name}' for channel '{channel.name}'.")
    except Exception as e:
        logger.exception(f"Failed to update channel permissions for '{channel.name}': {e}")
        raise