# Helpers/discord_api.py

from functools import partial

import discord
from utils.logging import get_logger

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
    user_limit: int | None = None,
    overwrites: dict | None = None,
) -> None:
    async def _task() -> None:
        return await guild.create_voice_channel(
            name=name,
            category=category,
            user_limit=user_limit,
            overwrites=overwrites or {},
        )

    try:
        future = await enqueue_task(_task)
        channel = await future
        logger.info(f"Created voice channel '{channel.name}' in '{category.name}'.")
        return channel
    except Exception:
        logger.exception(f"Failed to create voice channel '{name}'")
        raise


async def delete_channel(channel: discord.abc.GuildChannel) -> None:
    async def _task() -> None:
        # Check if the channel still exists before deleting
        if channel is None:
            logger.warning("Attempted to delete a channel that no longer exists.")
            return
        try:
            await channel.guild.fetch_channel(
                channel.id
            )  # Explicit check if the channel exists
            await channel.delete()
            logger.info(f"Deleted channel '{channel.name}' successfully.")
        except discord.NotFound:
            logger.warning(
                f"Channel '{channel.id}' not found. It may have already been deleted."
            )
        except discord.Forbidden:
            logger.exception(f"Bot lacks permissions to delete channel '{channel.id}'.")
        except discord.HTTPException:
            logger.exception(f"HTTP error while deleting channel '{channel.id}'")

    try:
        await enqueue_task(_task)
    except Exception:
        logger.exception(f"Failed to enqueue delete task for channel '{channel.id}'")


async def edit_channel(channel: discord.abc.GuildChannel, **kwargs) -> None:
    async def _task() -> None:
        # Verify channel still exists; skip if it doesn't
        try:
            await channel.guild.fetch_channel(channel.id)
        except discord.NotFound:
            logger.warning(f"Channel '{channel.id}' not found while editing; skipping.")
            return
        try:
            await channel.edit(**kwargs)
        except discord.Forbidden:
            logger.exception(f"Forbidden editing channel '{channel.id}'.")
        except discord.HTTPException:
            logger.exception(f"HTTP error while editing channel '{channel.id}'")

    try:
        await enqueue_task(_task)
        logger.info(
            f"Enqueued edit for channel '{getattr(channel, 'name', channel.id)}' with {kwargs}."
        )
    except Exception:
        logger.exception(
            f"Failed to enqueue edit for channel '{getattr(channel, 'name', channel.id)}'"
        )
        raise


async def move_member(member: discord.Member, channel: discord.VoiceChannel) -> None:
    async def _task() -> None:
        await member.move_to(channel)

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued move of '{member.display_name}' to '{channel.name}'.")
    except Exception:
        logger.exception(f"Failed to enqueue move for '{member.display_name}'")
        raise

        # -------------------------------------------------------------------------
        # Roles / Member editing
        # -------------------------------------------------------------------------


async def add_roles(member: discord.Member, *roles, reason: str | None = None) -> None:
    async def _task() -> None:
        await member.add_roles(*roles, reason=reason)

    try:
        await enqueue_task(_task)
        role_names = ", ".join(r.name for r in roles)
        logger.info(f"Enqueued add_roles for '{member.display_name}': {role_names}.")
    except Exception:
        logger.exception(
            f"Failed to enqueue add_roles for user '{member.display_name}'"
        )
        raise


async def remove_roles(
    member: discord.Member, *roles, reason: str | None = None
) -> None:
    async def _task() -> None:
        await member.remove_roles(*roles, reason=reason)

    try:
        await enqueue_task(_task)
        role_names = ", ".join(r.name for r in roles)
        logger.info(f"Enqueued remove_roles for '{member.display_name}': {role_names}.")
    except Exception as e:
        logger.exception(
            f"Failed to enqueue remove_roles for user '{member.display_name}': {e}"
        )
        raise


async def edit_member(member: discord.Member, **kwargs) -> None:
    async def _task() -> None:
        try:
            await member.edit(**kwargs)
        except discord.Forbidden:
            # Don’t bubble up; just log. This covers owner / hierarchy / missing perms.
            logger.warning(
                f"Forbidden editing '{member.display_name}' with {kwargs} (likely hierarchy/owner)."
            )
        except discord.NotFound:
            logger.warning(
                f"Member {member.id} not found while editing (left the guild?)."
            )
        except discord.HTTPException:
            logger.exception(f"HTTP error editing member {member.id}")
        except Exception:
            logger.exception(f"Unexpected error editing member {member.id}")

    try:
        await enqueue_task(_task)
        logger.info(f"Enqueued edit for user '{member.display_name}' with {kwargs}.")
    except Exception:
        logger.exception(f"Failed to enqueue edit for user '{member.display_name}'")
        raise

        # -------------------------------------------------------------------------
        # Slash Command interaction responses
        # -------------------------------------------------------------------------


async def send_message(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool = False,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> None:
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
    view: discord.ui.View,
) -> None:
    try:
        kwargs = {
            "content": content,
            "ephemeral": ephemeral,
            "embed": embed,
            "allowed_mentions": discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        }
        if view is not None:
            kwargs["view"] = view
        # Try to send the initial interaction response. There is a small race
        # where another task may have acknowledged the interaction first; in
        # that case Discord returns a specific error (HTTP code 40060). Try the
        # primary send and fall back to a follow-up when we detect that case.
        try:
            await interaction.response.send_message(**kwargs)
            logger.info(f"Sent message to {interaction.user.display_name}: {content}")
        except discord.HTTPException as e:
            code = getattr(e, "code", None)
            msg = str(e)
            if code == 40060 or "Interaction has already been acknowledged" in msg:
                try:
                    await interaction.followup.send(**kwargs)
                    logger.info(
                        f"Sent follow-up message after ack race to {interaction.user.display_name}: {content}"
                    )
                except Exception:
                    logger.exception(
                        f"Failed to send follow-up after initial send failed for {interaction.user.display_name}: {content}"
                    )
            else:
                raise
    except Exception:
        logger.exception("Failed to send message")


async def followup_send_message(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool = False,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> None:
    """
    Sends a follow-up message after you've already responded or deferred the interaction.
    """
    task = partial(
        followup_send_message_task, interaction, content, ephemeral, embed, view
    )
    await enqueue_task(task)


async def followup_send_message_task(
    interaction: discord.Interaction,
    content: str,
    ephemeral: bool,
    embed: discord.Embed,
    view: discord.ui.View,
) -> None:
    try:
        kwargs = {
            "content": content,
            "ephemeral": ephemeral,
            "embed": embed,
            "allowed_mentions": discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        }
        if view is not None:
            kwargs["view"] = view

        await interaction.followup.send(**kwargs)
        logger.info(
            f"Sent follow-up message to {interaction.user.display_name}: {content}"
        )
    except Exception:
        logger.exception("Failed to send follow-up message")

        # -------------------------------------------------------------------------
        # Channel text sends (e.g., channel.send)
        # -------------------------------------------------------------------------


async def channel_send_message(
    channel: discord.TextChannel,
    content: str,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> None:
    """
    Enqueues a message to be sent to a specific channel.
    """
    task = partial(channel_send_message_task, channel, content, embed, view)
    await enqueue_task(task)


async def channel_send_message_task(
    channel: discord.TextChannel,
    content: str,
    embed: discord.Embed,
    view: discord.ui.View,
) -> None:
    try:
        kwargs = {
            "content": content,
            "allowed_mentions": discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        }
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view

        await channel.send(**kwargs)
        logger.info(f"Sent message to channel '{channel.name}': {content}")
    except Exception:
        logger.exception(f"Failed to send message to channel '{channel.name}'")

        # -------------------------------------------------------------------------
        # Direct Messages (DM) to Members
        # -------------------------------------------------------------------------


async def send_direct_message(
    member: discord.Member, content: str, embed: discord.Embed | None = None
) -> None:
    """
    Enqueues a direct message (DM) to a member.
    """
    task = partial(send_direct_message_task, member, content, embed)
    await enqueue_task(task)


async def send_direct_message_task(
    member: discord.Member, content: str, embed: discord.Embed
) -> None:
    try:
        if embed is not None:
            await member.send(content, embed=embed)
        else:
            await member.send(content)
        logger.info(f"Sent DM to '{member.display_name}': {content}")
    except discord.Forbidden:
        logger.warning(f"Cannot send DM to '{member.display_name}' (forbidden).")
    except Exception as e:
        logger.exception("Failed to send DM to '%s'", member.display_name, exc_info=e)

        # -------------------------------------------------------------------------
        # Editing Messages
        # -------------------------------------------------------------------------


async def edit_message(
    interaction: discord.Interaction,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> None:
    """
    Enqueues a message edit to be sent as part of a follow-up interaction.
    """
    task = partial(edit_message_task, interaction, content, embed, view)
    await enqueue_task(task)


async def edit_message_task(
    interaction: discord.Interaction,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> None:
    try:
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view

        if not interaction.response.is_done():
            await interaction.response.send_message(**kwargs)
            logger.info(
                f"Sent initial interaction response to {interaction.user.display_name}: {content}"
            )
        else:
            await interaction.edit_original_response(**kwargs)
            logger.info(
                f"Edited interaction response for {interaction.user.display_name}: {content}"
            )
    except discord.NotFound as e:
        if "Unknown Webhook" in str(e):
            logger.exception(
                "Attempted to edit a message using an unknown webhook. Interaction may have expired."
            )
        else:
            logger.exception("Failed to edit message", exc_info=e)
    except Exception as e:
        logger.exception("Failed to edit message", exc_info=e)
