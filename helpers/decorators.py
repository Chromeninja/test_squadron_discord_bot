"""Reusable permission check decorators for Discord app commands."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

import discord

from helpers.permissions_helper import (
    PERMISSION_DENIED_MESSAGE,
    PermissionLevel,
    get_permission_level,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable])


async def _send_permission_denied(interaction: discord.Interaction) -> None:
    """Send the standardized permission error message."""

    if interaction.response.is_done():
        await interaction.followup.send(PERMISSION_DENIED_MESSAGE, ephemeral=True)
    else:
        await interaction.response.send_message(
            PERMISSION_DENIED_MESSAGE,
            ephemeral=True,
        )


def _resolve_bot(self) -> discord.Client | None:
    """Try to find a bot/client reference on the cog or nested helper."""

    bot = getattr(self, "bot", None)
    if bot:
        return bot
    voice_cog = getattr(self, "voice_cog", None)
    if voice_cog:
        return getattr(voice_cog, "bot", None)
    return None


def require_permission_level(min_level: PermissionLevel) -> Callable[[F], F]:
    """Decorator factory that limits commands to users with minimum permission level.

    Uses new hierarchy system with support for all 6 role levels:
    - PermissionLevel.BOT_OWNER (6): Bot owner only
    - PermissionLevel.BOT_ADMIN (5): Bot admins + owner
    - PermissionLevel.DISCORD_MANAGER (4): Discord managers + higher
    - PermissionLevel.MODERATOR (3): Moderators + higher
    - PermissionLevel.STAFF (2): Staff + higher
    - PermissionLevel.USER (1): All users (no restriction)

    Args:
        min_level: Minimum permission level required to use command

    Returns:
        Decorator function

    Example:
        @app_commands.command()
        @require_permission_level(PermissionLevel.MODERATOR)
        async def my_command(self, interaction: discord.Interaction):
            ...
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            bot = _resolve_bot(self)
            if not bot or not isinstance(interaction.user, discord.Member):
                logger.warning(
                    "Permission check failed for %s: unable to resolve bot/member",
                    func.__qualname__,
                )
                await _send_permission_denied(interaction)
                return None

            guild = interaction.guild
            if guild is None:
                logger.warning(
                    "Permission check failed for %s: interaction without guild",
                    func.__qualname__,
                )
                await _send_permission_denied(interaction)
                return None

            level = await get_permission_level(bot, interaction.user, guild)
            if level < min_level:
                logger.warning(
                    (
                        "Permission denied for %s: user_id=%s level=%s required=%s "
                        "guild_id=%s"
                    ),
                    func.__qualname__,
                    interaction.user.id,
                    level.name,
                    min_level.name,
                    guild.id,
                )
                await _send_permission_denied(interaction)
                return None

            logger.debug(
                "Permission granted for %s: user_id=%s level=%s guild_id=%s",
                func.__qualname__,
                interaction.user.id,
                level.name,
                guild.id,
            )

            return await func(self, interaction, *args, **kwargs)

        return wrapper  # type: ignore[misc]

    return decorator


def require_bot_admin() -> Callable[[F], F]:
    """Decorator that limits a command to configured bot admins or higher."""

    return require_permission_level(PermissionLevel.BOT_ADMIN)


def require_admin() -> Callable[[F], F]:
    """Decorator that limits a command to moderators or higher.

    Deprecated alias retained for backward compatibility with legacy cogs.
    """

    return require_permission_level(PermissionLevel.MODERATOR)


def require_bot_owner() -> Callable[[F], F]:
    """Decorator that limits a command to the bot owner only."""
    return require_permission_level(PermissionLevel.BOT_OWNER)


def require_discord_manager() -> Callable[[F], F]:
    """Decorator that limits a command to discord managers or higher."""
    return require_permission_level(PermissionLevel.DISCORD_MANAGER)


def require_moderator() -> Callable[[F], F]:
    """Decorator that limits a command to moderators or higher."""
    return require_permission_level(PermissionLevel.MODERATOR)


def require_staff() -> Callable[[F], F]:
    """Decorator that limits a command to staff or higher."""
    return require_permission_level(PermissionLevel.STAFF)


__all__ = [
    "require_admin",
    "require_bot_admin",
    "require_bot_owner",
    "require_discord_manager",
    "require_moderator",
    "require_permission_level",
    "require_staff",
]
