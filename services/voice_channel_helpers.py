"""Pure and low-coupling helper functions for voice service workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    import logging


def get_member_count(
    channel_or_id: discord.VoiceChannel | discord.StageChannel | int | None,
    *,
    bot: discord.Client | None,
    voice_channel_members: dict[int, set[int]],
    logger: logging.Logger,
) -> int:
    """Return member count for a voice-like channel with cache fallback."""
    if channel_or_id is None:
        return 0

    channel: discord.VoiceChannel | discord.StageChannel | None
    channel_id: int | None

    if isinstance(channel_or_id, int):
        channel_id = channel_or_id
        channel_candidate = bot.get_channel(channel_id) if bot else None
        if isinstance(channel_candidate, (discord.VoiceChannel, discord.StageChannel)):
            channel = channel_candidate
        else:
            channel = None
    else:
        channel = channel_or_id
        channel_id = getattr(channel, "id", None)

    try:
        if channel and hasattr(channel, "members"):
            return len(channel.members)
    except Exception:
        logger.debug("Failed to read channel.members for channel %s", channel_id)

    if channel_id is not None:
        cached = voice_channel_members.get(channel_id)
        if cached is not None:
            return len(cached)

    return 0


def classify_old_channel(member_count: int) -> str:
    """Classify old-channel action during ownership transition."""
    if member_count > 0:
        return "orphan"
    return "delete"


def sanitize_overwrite(
    overwrite: discord.PermissionOverwrite,
    bot_perms: discord.Permissions,
) -> discord.PermissionOverwrite:
    """Remove allowed permission bits the bot itself lacks."""
    allow, deny = overwrite.pair()
    sanitized_allow = discord.Permissions(allow.value & bot_perms.value)
    return discord.PermissionOverwrite.from_pair(sanitized_allow, deny)


def get_user_game_name(member: discord.Member, logger: logging.Logger) -> str | None:
    """Return active game/activity name for a member if available."""
    try:
        if member.activity and hasattr(member.activity, "name"):
            return member.activity.name
    except Exception:
        logger.debug("Failed to read activity for member %s", member.id)
    return None


def validate_jtc_permissions(
    category: discord.CategoryChannel | None,
    *,
    bot: discord.Client | None,
    logger: logging.Logger,
) -> tuple[bool, str | None]:
    """Validate bot permissions required for JTC channel operations."""
    try:
        logger.debug(
            "Validating JTC permissions for category %s",
            category.id if category else "None",
        )

        if category is None:
            logger.warning("JTC permission check failed: category is None")
            return False, "Category does not exist"

        if not bot or not bot.user:
            logger.warning("JTC permission check failed: bot not available")
            return False, "Bot instance or bot user not available"

        guild = category.guild
        bot_member = guild.get_member(bot.user.id)
        if bot_member is None:
            logger.warning(
                "JTC permission check failed: bot member not found in guild %s",
                guild.id,
            )
            return False, "Bot member not found in guild"

        perms = category.permissions_for(bot_member)
        if not perms.view_channel:
            logger.warning(
                "Missing 'View Channel' permission in category '%s' (%s)",
                category.name,
                category.id,
                extra={"guild_id": guild.id, "category_id": category.id},
            )
            return (
                False,
                f"Bot missing 'View Channel' permission in category '{category.name}'",
            )

        if not perms.manage_channels:
            logger.warning(
                "Missing 'Manage Channels' permission in category '%s' (%s)",
                category.name,
                category.id,
                extra={"guild_id": guild.id, "category_id": category.id},
            )
            return (
                False,
                f"Bot missing 'Manage Channels' permission in category '{category.name}'",
            )

        if not perms.manage_roles:
            logger.warning(
                "Missing 'Manage Permissions' (manage_roles) in category '%s' (%s)",
                category.name,
                category.id,
                extra={"guild_id": guild.id, "category_id": category.id},
            )
            return (
                False,
                f"Bot missing 'Manage Permissions' permission in category '{category.name}'",
            )

        guild_perms = bot_member.guild_permissions
        if not guild_perms.move_members:
            logger.warning(
                "Missing 'Move Members' permission in guild %s",
                guild.id,
                extra={"guild_id": guild.id},
            )
            return (
                False,
                f"Bot missing 'Move Members' permission in guild '{guild.name}'",
            )

        logger.debug(
            "JTC permission validation passed for category %s",
            category.name,
            extra={"guild_id": guild.id, "category_id": category.id},
        )
        return True, None

    except Exception as error:
        logger.exception("Error validating JTC permissions", exc_info=error)
        return False, str(error)
