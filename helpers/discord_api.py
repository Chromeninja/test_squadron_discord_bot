# helpers/discord_api.py

import discord
from functools import partial
from helpers.logger import get_logger
from helpers.task_queue import enqueue_task

logger = get_logger(__name__)

"""
Centralized module for all Discord API calls.
Enqueues each call so they're rate-limited via task_queue.py.
"""

# -------------------------------------------------------------------------
# Channel creation, deletion, editing, and moving members
# -------------------------------------------------------------------------

async def create_voice_channel(
    guild: discord.Guild,
    name: str,
    category: discord.CategoryChannel,
    *,
    user_limit: int = None,
    overwrites: dict = None
):
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
    async def _task():
        await channel.delete()

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued channel delete for '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to enqueue delete for channel '{channel.name}': {e}")
        raise

async def edit_channel(channel: discord.abc.GuildChannel, **kwargs):
    async def _task():
        await channel.edit(**kwargs)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued edit for channel '{channel.name}' with {kwargs}.")
    except Exception as e:
        logger.error(f"Failed to enqueue edit for channel '{channel.name}': {e}")
        raise

async def move_member(member: discord.Member, channel: discord.VoiceChannel):
    async def _task():
        await member.move_to(channel)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued move of '{member.display_name}' to '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to enqueue move for '{member.display_name}': {e}")
        raise

# -------------------------------------------------------------------------
# Roles / Member editing
# -------------------------------------------------------------------------

async def add_roles(member: discord.Member, *roles, reason: str = None):
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
    async def _task():
        await member.edit(**kwargs)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued edit for user '{member.display_name}' with {kwargs}.")
    except Exception as e:
        logger.error(f"Failed to enqueue edit for user '{member.display_name}': {e}")
        raise

# -------------------------------------------------------------------------
# Slash Command interaction responses
# -------------------------------------------------------------------------

async def send_message(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool = False,
    embed: discord.Embed = None,
    view: discord.ui.View = None
):
    """
    Sends an ephemeral (or public) message as the immediate slash command response
    (i.e., uses interaction.response.send_message).
    """
    task = partial(send_message_task, interaction, content, ephemeral, embed, view)
    await enqueue_task(task)

async def send_message_task(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool,
    embed: discord.Embed,
    view: discord.ui.View
):
    try:
        kwargs = {
            "content": content,
            "ephemeral": ephemeral,
            "embed": embed,
        }
        if view is not None:
            kwargs["view"] = view

        await interaction.response.send_message(**kwargs)
        logger.info(f"Sent message to {interaction.user.display_name}: {content}")
    except Exception as e:
        logger.exception(f"Failed to send message: {e}")

async def followup_send_message(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool = False,
    embed: discord.Embed = None,
    view: discord.ui.View = None
):
    """
    Sends a follow-up message after you've already responded or deferred the interaction.
    """
    task = partial(followup_send_message_task, interaction, content, ephemeral, embed, view)
    await enqueue_task(task)

async def followup_send_message_task(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool,
    embed: discord.Embed,
    view: discord.ui.View
):
    try:
        kwargs = {
            "content": content,
            "ephemeral": ephemeral,
            "embed": embed,
        }
        if view is not None:
            kwargs["view"] = view

        await interaction.followup.send(**kwargs)
        logger.info(f"Sent follow-up message to {interaction.user.display_name}: {content}")
    except Exception as e:
        logger.exception(f"Failed to send follow-up message: {e}")

# -------------------------------------------------------------------------
# Channel text sends (e.g., channel.send)
# -------------------------------------------------------------------------

async def channel_send_message(
    channel: discord.TextChannel,
    content: str,
    embed: discord.Embed = None,
    view: discord.ui.View = None
):
    """
    Enqueues a message to be sent to a specific channel.
    """
    task = partial(channel_send_message_task, channel, content, embed, view)
    await enqueue_task(task)

async def channel_send_message_task(
    channel: discord.TextChannel,
    content: str,
    embed: discord.Embed,
    view: discord.ui.View
):
    try:
        kwargs = {"content": content}
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view

        await channel.send(**kwargs)
        logger.info(f"Sent message to channel '{channel.name}': {content}")
    except Exception as e:
        logger.exception(f"Failed to send message to channel '{channel.name}': {e}")

# -------------------------------------------------------------------------
# Direct Messages (DM) to Members
# -------------------------------------------------------------------------

async def send_direct_message(
    member: discord.Member,
    content: str,
    embed: discord.Embed = None
):
    """
    Enqueues a direct message (DM) to a member.
    """
    task = partial(send_direct_message_task, member, content, embed)
    await enqueue_task(task)

async def send_direct_message_task(
    member: discord.Member,
    content: str,
    embed: discord.Embed
):
    try:
        if embed is not None:
            await member.send(content, embed=embed)
        else:
            await member.send(content)
        logger.info(f"Sent DM to '{member.display_name}': {content}")
    except discord.Forbidden:
        logger.warning(f"Cannot send DM to '{member.display_name}' (forbidden).")
    except Exception as e:
        logger.exception(f"Failed to send DM to '{member.display_name}': {e}")
