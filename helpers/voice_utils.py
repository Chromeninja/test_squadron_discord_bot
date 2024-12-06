# helpers/voice_utils.py

import discord
from helpers.database import Database
from helpers.logger import get_logger
from aiolimiter import AsyncLimiter

logger = get_logger(__name__)

# Initialize a global rate limiter
# Discord's global rate limit is 50 requests per second
# Adjust based on observed limits and needs
api_limiter = AsyncLimiter(max_rate=45, time_period=1)  # Slightly below 50 to provide a buffer

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
        cursor = await db.execute("SELECT voice_channel_id FROM user_voice_channels WHERE owner_id = ?", (member.id,))
        row = await cursor.fetchone()
        if row:
            channel_id = row[0]
            channel = bot.get_channel(channel_id)
            if channel:
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
        **kwargs: The settings to update (channel_name, user_limit, permissions).
    """
    channel_name = kwargs.get('channel_name', None)
    user_limit = kwargs.get('user_limit', None)
    lock = kwargs.get('lock', None)

    async with Database.get_connection() as db:
        if channel_name is not None:
            await db.execute(
                "INSERT OR REPLACE INTO channel_settings (user_id, channel_name) VALUES (?, ?)",
                (user_id, channel_name)
            )

        if user_limit is not None:
            await db.execute(
                "INSERT OR REPLACE INTO channel_settings (user_id, user_limit) VALUES (?, ?)",
                (user_id, user_limit)
            )

        if lock is not None:
            await db.execute(
                "INSERT OR REPLACE INTO channel_settings (user_id, lock) VALUES (?, ?)",
                (user_id, lock)
            )

        await db.commit()

async def set_channel_permission(user_id, target_id, target_type, permission):
    async with Database.get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
            VALUES (?, ?, ?, ?)
        """, (user_id, target_id, target_type, permission))
        await db.commit()

async def remove_channel_permission(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute("""
            DELETE FROM channel_permissions
            WHERE user_id = ? AND target_id = ? AND target_type = ?
        """, (user_id, target_id, target_type))
        await db.commit()

async def get_channel_permissions(user_id):
    async with Database.get_connection() as db:
        cursor = await db.execute("""
            SELECT target_id, target_type, permission FROM channel_permissions
            WHERE user_id = ?
        """, (user_id,))
        permissions = await cursor.fetchall()
        return permissions

async def set_ptt_setting(user_id, target_id, target_type, ptt_enabled):
    async with Database.get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO channel_ptt_settings (user_id, target_id, target_type, ptt_enabled)
            VALUES (?, ?, ?, ?)
        """, (user_id, target_id if target_id is not None else 0, target_type, ptt_enabled))
        await db.commit()

async def remove_ptt_setting(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute("""
            DELETE FROM channel_ptt_settings
            WHERE user_id = ? AND target_id = ? AND target_type = ?
        """, (user_id, target_id, target_type))
        await db.commit()

async def get_ptt_settings(user_id):
    async with Database.get_connection() as db:
        cursor = await db.execute("""
            SELECT target_id, target_type, ptt_enabled FROM channel_ptt_settings
            WHERE user_id = ?
        """, (user_id,))
        ptt_settings = await cursor.fetchall()
        return ptt_settings

async def safe_edit_channel(channel: discord.VoiceChannel, **kwargs):
    """
    Safely edits a Discord channel with rate limiting.

    Args:
        channel (discord.VoiceChannel): The channel to edit.
        **kwargs: Attributes to edit.
    """
    async with api_limiter:
        try:
            await channel.edit(**kwargs)
            logger.info(f"Edited channel '{channel.name}' with {kwargs}")
        except discord.HTTPException as e:
            logger.error(f"Failed to edit channel '{channel.name}': {e}")
            raise

async def safe_delete_channel(channel: discord.VoiceChannel):
    """
    Safely deletes a Discord channel with rate limiting.

    Args:
        channel (discord.VoiceChannel): The channel to delete.
    """
    async with api_limiter:
        try:
            await channel.delete()
            logger.info(f"Deleted channel '{channel.name}'")
        except discord.HTTPException as e:
            logger.error(f"Failed to delete channel '{channel.name}': {e}")
            raise

async def safe_create_voice_channel(guild: discord.Guild, name: str, category: discord.CategoryChannel, user_limit: int = None, overwrites: dict = None):
    """
    Safely creates a Discord voice channel with rate limiting.

    Args:
        guild (discord.Guild): The guild where the channel will be created.
        name (str): The name of the channel.
        category (discord.CategoryChannel): The category under which the channel will be created.
        user_limit (int, optional): The user limit for the channel.
        overwrites (dict, optional): Permission overwrites.

    Returns:
        discord.VoiceChannel: The created voice channel.
    """
    async with api_limiter:
        try:
            channel = await guild.create_voice_channel(
                name=name,
                category=category,
                user_limit=user_limit,
                overwrites=overwrites or {}
            )
            logger.info(f"Created voice channel '{channel.name}' in category '{category.name}'")
            return channel
        except discord.HTTPException as e:
            logger.error(f"Failed to create voice channel '{name}': {e}")
            raise

async def safe_move_member(member: discord.Member, channel: discord.VoiceChannel):
    """
    Safely moves a member to a voice channel with rate limiting.

    Args:
        member (discord.Member): The member to move.
        channel (discord.VoiceChannel): The target voice channel.
    """
    async with api_limiter:
        try:
            await member.move_to(channel)
            logger.info(f"Moved member '{member.display_name}' to channel '{channel.name}'")
        except discord.HTTPException as e:
            logger.error(f"Failed to move member '{member.display_name}' to channel '{channel.name}': {e}")
            raise
