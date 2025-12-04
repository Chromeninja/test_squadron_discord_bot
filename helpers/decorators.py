"""Reusable permission check decorators for Discord app commands."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar, cast

import discord

from helpers.permissions_helper import (
    PERMISSION_DENIED_MESSAGE,
    PermissionLevel,
    get_permission_level,
    # Legacy imports for backward compatibility
    is_bot_admin_only,
    is_lead_moderator_or_higher,
)

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


async def _call_bot_admin(
    bot: discord.Client,
    member: discord.Member,
    guild: discord.Guild,
) -> bool:
    """Check bot admin permissions (legacy wrapper for backward compatibility)."""
    checker = getattr(bot, "has_bot_admin_permissions", None)
    if callable(checker):
        checker_callable = cast(
            "Callable[[discord.Member, discord.Guild | None], Awaitable[bool]]",
            checker,
        )
        return await checker_callable(member, guild)

    return await is_bot_admin_only(bot, member, guild)


async def _call_admin_or_higher(
    bot: discord.Client,
    member: discord.Member,
    guild: discord.Guild,
) -> bool:
    """Check moderator+ permissions (legacy wrapper for backward compatibility)."""
    checker = getattr(bot, "has_admin_permissions", None)
    if callable(checker):
        checker_callable = cast(
            "Callable[[discord.Member, discord.Guild | None], Awaitable[bool]]",
            checker,
        )
        return await checker_callable(member, guild)

    return await is_lead_moderator_or_higher(bot, member, guild)


async def _check_permission_level(
    bot: discord.Client,
    member: discord.Member,
    guild: discord.Guild,
    min_level: PermissionLevel,
) -> bool:
    """Check if member has minimum permission level using new hierarchy system."""
    level = await get_permission_level(bot, member, guild)
    return level >= min_level


def _permission_wrapper(
    predicate: Callable[
        [discord.Client, discord.Member, discord.Guild],
        Awaitable[bool],
    ],
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            bot = _resolve_bot(self)
            if not bot or not isinstance(interaction.user, discord.Member):
                await _send_permission_denied(interaction)
                return None

            guild = interaction.guild
            if guild is None:
                await _send_permission_denied(interaction)
                return None

            has_permission = await predicate(bot, interaction.user, guild)
            if not has_permission:
                await _send_permission_denied(interaction)
                return None

            return await func(self, interaction, *args, **kwargs)

        return wrapper  # type: ignore[misc]

    return decorator


def require_bot_admin() -> Callable[[F], F]:
    """Decorator that limits a command to configured bot admins.

    DEPRECATED: Use require_permission_level(PermissionLevel.BOT_ADMIN) instead.
    Kept for backward compatibility with existing commands.
    """
    return _permission_wrapper(_call_bot_admin)


def require_admin() -> Callable[[F], F]:
    """Decorator that limits a command to moderators or higher.

    DEPRECATED: Use require_permission_level(PermissionLevel.MODERATOR) instead.
    Kept for backward compatibility with existing commands.
    """
    return _permission_wrapper(_call_admin_or_higher)


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
    async def predicate(
        bot: discord.Client,
        member: discord.Member,
        guild: discord.Guild,
    ) -> bool:
        return await _check_permission_level(bot, member, guild, min_level)

    return _permission_wrapper(predicate)


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
    # Legacy decorators (deprecated, use new ones above)
    "require_admin",
    "require_bot_admin",
    "require_bot_owner",
    "require_discord_manager",
    "require_moderator",
    # New hierarchy decorators (preferred)
    "require_permission_level",
    "require_staff",
]
