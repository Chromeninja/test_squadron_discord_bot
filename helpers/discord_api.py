# helpers/discord_api.py

import discord
from helpers.logger import get_logger
from helpers.task_queue import enqueue_task

logger = get_logger(__name__)

"""
Centralized module for all Discord API calls.
Enqueues each call so they're rate-limited via task_queue.py.
"""

async def create_voice_channel(guild: discord.Guild, name: str, category: discord.CategoryChannel, *,
                               user_limit: int = None, overwrites: dict = None):
    """
    Creates a voice channel in the specified guild/category.
    """
    async def _task():
        return await guild.create_voice_channel(
            name=name,
            category=category,
            user_limit=user_limit,
            overwrites=overwrites or {}
        )
    try:
        future = await enqueue_task(_task)
        channel = await future
        logger.info(f"Created voice channel '{channel.name}' in '{category.name}'.")
        return channel
    except Exception as e:
        logger.error(f"Failed to create voice channel '{name}': {e}")
        raise

async def delete_channel(channel: discord.abc.GuildChannel):
    """
    Deletes a channel.
    """
    async def _task():
        await channel.delete()

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued channel delete for '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to enqueue delete for channel '{channel.name}': {e}")
        raise

async def edit_channel(channel: discord.abc.GuildChannel, **kwargs):
    """
    Edits a channel (name, overwrites, user_limit, etc.).
    """
    async def _task():
        await channel.edit(**kwargs)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued edit for channel '{channel.name}' with {kwargs}.")
    except Exception as e:
        logger.error(f"Failed to enqueue edit for channel '{channel.name}': {e}")
        raise

async def move_member(member: discord.Member, channel: discord.VoiceChannel):
    """
    Moves a member to a voice channel.
    """
    async def _task():
        await member.move_to(channel)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued move of '{member.display_name}' to '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to enqueue move for '{member.display_name}': {e}")
        raise

async def add_roles(member: discord.Member, *roles, reason: str = None):
    """
    Adds one or more roles to a member.
    """
    async def _task():
        await member.add_roles(*roles, reason=reason)

    try:
        await enqueue_task(_task)
        role_names = ", ".join(r.name for r in roles)
        logger.info(f"Enqueued add_roles for '{member.display_name}': {role_names}.")
    except Exception as e:
        logger.error(f"Failed to enqueue add_roles for user '{member.display_name}': {e}")
        raise

async def remove_roles(member: discord.Member, *roles, reason: str = None):
    """
    Removes one or more roles from a member.
    """
    async def _task():
        await member.remove_roles(*roles, reason=reason)

    try:
        await enqueue_task(_task)
        role_names = ", ".join(r.name for r in roles)
        logger.info(f"Enqueued remove_roles for '{member.display_name}': {role_names}.")
    except Exception as e:
        logger.error(f"Failed to enqueue remove_roles for user '{member.display_name}': {e}")
        raise

async def edit_member(member: discord.Member, **kwargs):
    """
    Edits a member (nickname, etc.).
    """
    async def _task():
        await member.edit(**kwargs)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued edit for user '{member.display_name}' with {kwargs}.")
    except Exception as e:
        logger.error(f"Failed to enqueue edit for user '{member.display_name}': {e}")
        raise
