"""Reusable permission check decorators for Discord app commands."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar, cast

import discord

from helpers.permissions_helper import (
    PERMISSION_DENIED_MESSAGE,
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
    checker = getattr(bot, "has_admin_permissions", None)
    if callable(checker):
        checker_callable = cast(
            "Callable[[discord.Member, discord.Guild | None], Awaitable[bool]]",
            checker,
        )
        return await checker_callable(member, guild)

    return await is_lead_moderator_or_higher(bot, member, guild)


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
    """Decorator that limits a command to configured bot admins."""

    return _permission_wrapper(_call_bot_admin)


def require_admin() -> Callable[[F], F]:
    """Decorator that limits a command to lead moderators or higher."""

    return _permission_wrapper(_call_admin_or_higher)


__all__ = ["require_admin", "require_bot_admin"]
