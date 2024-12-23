# helpers/voice_utils.py

import discord
from helpers.database import Database
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
    # Fetch the channel ID from the database
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT voice_channel_id FROM user_voice_channels WHERE owner_id = ?",
            (member.id,)
        )
        row = await cursor.fetchone()
        if row:
            channel_id = row[0]
            channel = bot.get_channel(channel_id)

            # Attempt to fetch channel if not cached
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except discord.NotFound:
                    logger.warning(f"Channel with ID {channel_id} not found.")
                    return None
                except discord.Forbidden:
                    logger.warning(f"Forbidden to fetch channel with ID {channel_id}.")
                    return None
                except discord.HTTPException as e:
                    logger.error(f"Failed to fetch channel {channel_id}: {e}")
                    return None
            return channel
    return None

def get_user_game_name(member):
    """
    Retrieves the name of the game the user is currently playing.

    Args:
        member: The Discord member.

    Returns:
        The name of the game the user is playing, or None if not playing any.
    """
    for activity in member.activities:
        if activity.type == discord.ActivityType.playing:
            return activity.name
    return None

async def update_channel_settings(user_id, **kwargs):
    """
    Updates the channel settings for a user.

    Args:
        user_id (int): The Discord user ID.
        **kwargs: The settings to update (channel_name, user_limit, lock).
    """
    fields = []
    values = []

    if 'channel_name' in kwargs:
        fields.append("channel_name = ?")
        values.append(kwargs['channel_name'])
    if 'user_limit' in kwargs:
        fields.append("user_limit = ?")
        values.append(kwargs['user_limit'])
    if 'lock' in kwargs:
        fields.append("lock = ?")
        values.append(kwargs['lock'])

    if not fields:
        return

    values.append(user_id)

    query = f"UPDATE channel_settings SET {', '.join(fields)} WHERE user_id = ?"

    async with Database.get_connection() as db:
        await db.execute("INSERT OR IGNORE INTO channel_settings (user_id) VALUES (?)", (user_id,))
        await db.execute(query, tuple(values))
        await db.commit()

async def set_channel_permission(user_id, target_id, target_type, permission):
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id, target_type, permission)
        )
        await db.commit()

async def remove_channel_permission(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute(
            """
            DELETE FROM channel_permissions
            WHERE user_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, target_id, target_type)
        )
        await db.commit()

async def get_channel_permissions(user_id):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT target_id, target_type, permission
            FROM channel_permissions
            WHERE user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchall()

async def set_ptt_setting(user_id, target_id, target_type, ptt_enabled):
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_ptt_settings
            (user_id, target_id, target_type, ptt_enabled)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id if target_id is not None else 0, target_type, ptt_enabled)
        )
        await db.commit()

async def remove_ptt_setting(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute(
            """
            DELETE FROM channel_ptt_settings
            WHERE user_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, target_id, target_type)
        )
        await db.commit()

async def get_ptt_settings(user_id):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT target_id, target_type, ptt_enabled
            FROM channel_ptt_settings
            WHERE user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchall()
