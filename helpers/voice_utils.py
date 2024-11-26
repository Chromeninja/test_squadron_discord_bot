# helpers/voice_utils.py

import discord
from helpers.database import Database
import json
from helpers.logger import get_logger

logger = get_logger(__name__)

async def get_user_channel(bot, member):
    """
    Retrieves the voice channel owned by the user.

    Args:
        bot: The bot instance.
        member: The Discord member.

    Returns:
        The voice channel owned by the user, or None if not found.
    """
    async with Database.get_connection() as db:
        cursor = await db.execute("SELECT voice_channel_id FROM user_voice_channels WHERE user_id = ?", (member.id,))
        row = await cursor.fetchone()
        if not row:
            return None
        channel_id = row[0]
        channel = bot.get_channel(channel_id)
        return channel

def get_user_game_name(member):
    """
    Retrieves the name of the game the user is currently playing.

    Args:
        member: The Discord member.

    Returns:
        The name of the game the user is playing, or None if not playing any.
    """
    for activity in member.activities:
        if isinstance(activity, discord.Game):
            return activity.name
    return None

async def update_channel_settings(user_id, **kwargs):
    """
    Updates the channel settings for a user.

    Args:
        user_id (int): The Discord user ID.
        **kwargs: The settings to update (channel_name, user_limit, permissions).
    """
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT channel_name, user_limit, permissions FROM channel_settings WHERE user_id = ?",
            (user_id,)
        )
        settings_row = await cursor.fetchone()
        if settings_row:
            channel_name, user_limit, permissions = settings_row
            if permissions and not isinstance(permissions, dict):
                permissions = json.loads(permissions)
        else:
            channel_name = None
            user_limit = None
            permissions = None

        # Update settings with provided kwargs
        channel_name = kwargs.get('channel_name', channel_name)
        user_limit = kwargs.get('user_limit', user_limit)
        permissions = kwargs.get('permissions', permissions)

        # Ensure permissions are stored as JSON string
        if permissions and isinstance(permissions, dict):
            permissions = json.dumps(permissions)

        await db.execute(
            "INSERT OR REPLACE INTO channel_settings (user_id, channel_name, user_limit, permissions) VALUES (?, ?, ?, ?)",
            (user_id, channel_name, user_limit, permissions)
        )
        await db.commit()
