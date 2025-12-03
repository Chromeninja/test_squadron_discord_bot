"""
Utilities for building structured logging context from Discord objects.

Provides helper functions to extract guild_id, user_id, channel_id, etc.
from Discord.py objects for consistent logging across the bot.
"""

from typing import Any

import discord
from discord.ext import commands


def get_context_extra(
    ctx: commands.Context | discord.Interaction | None = None,
    guild: discord.Guild | None = None,
    user: discord.User | discord.Member | None = None,
    channel: discord.abc.GuildChannel | discord.Thread | None = None,
    **additional: Any,
) -> dict[str, Any]:
    """
    Build a structured logging extra dict from Discord objects.

    Args:
        ctx: Command context or interaction (extracts guild, user, channel if provided)
        guild: Guild object (overrides ctx.guild if provided)
        user: User or Member object (overrides ctx.user if provided)
        channel: Channel object (overrides ctx.channel if provided)
        **additional: Any additional key-value pairs to include

    Returns:
        Dict with guild_id, user_id, channel_id, and any additional fields

    Examples:
        # From command context
        logger.info("Command executed", extra=get_context_extra(ctx, command_name="verify"))

        # From interaction
        logger.info("Button clicked", extra=get_context_extra(interaction, button_id="recheck"))

        # Manual composition
        logger.info("Manual event", extra=get_context_extra(guild=guild, user=member))
    """
    extra: dict[str, Any] = {}

    # Extract from context/interaction if provided
    if ctx is not None:
        # Extract guild, user, channel from context
        guild = guild or getattr(ctx, "guild", None)
        user = user or getattr(ctx, "user", None) or getattr(ctx, "author", None)
        channel = channel or getattr(ctx, "channel", None)

        # Extract command name if available
        command = getattr(ctx, "command", None)
        if command:
            extra["command_name"] = command.qualified_name

    # Add IDs if objects are present
    if guild:
        extra["guild_id"] = str(guild.id)
    if user:
        extra["user_id"] = str(user.id)
    if channel:
        extra["channel_id"] = str(channel.id)

    # Merge any additional fields
    extra.update(additional)

    return extra


def get_interaction_extra(
    interaction: discord.Interaction, **additional: Any
) -> dict[str, Any]:
    """
    Convenience wrapper for get_context_extra specifically for interactions.

    Args:
        interaction: Discord interaction object
        **additional: Any additional key-value pairs

    Returns:
        Structured logging extra dict
    """
    return get_context_extra(ctx=interaction, **additional)


def get_command_extra(ctx: commands.Context, **additional: Any) -> dict[str, Any]:
    """
    Convenience wrapper for get_context_extra specifically for command contexts.

    Args:
        ctx: Discord command context
        **additional: Any additional key-value pairs

    Returns:
        Structured logging extra dict
    """
    return get_context_extra(ctx=ctx, **additional)
