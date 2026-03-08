"""
Utilities for managing voice channel permissions.

This module provides functions for asserting and enforcing permissions
on user-created voice channels.
"""

import discord  # type: ignore[import-not-found]

from helpers.permissions_helper import FEATURE_CONFIG
from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)


def _get_hierarchy_blocking_roles(
    overwrites: dict[object, discord.PermissionOverwrite],
    bot_member: discord.Member,
    default_role: discord.Role,
) -> list[str]:
    """Return role names that the bot cannot manage due to hierarchy."""
    bot_top_role = getattr(bot_member, "top_role", None)
    bot_position = getattr(bot_top_role, "position", None)
    if not isinstance(bot_position, int):
        return []

    default_role_id = getattr(default_role, "id", None)
    blocked_roles: list[str] = []

    for target in overwrites:
        target_position = getattr(target, "position", None)
        target_name = getattr(target, "name", None)
        target_id = getattr(target, "id", None)

        if target_id == default_role_id:
            continue
        if not isinstance(target_position, int) or not isinstance(target_name, str):
            continue
        if target_position >= bot_position:
            blocked_roles.append(target_name)

    return sorted(set(blocked_roles))


async def assert_base_permissions(
    channel: discord.VoiceChannel,
    bot_member: discord.Member,
    owner_member: discord.Member,
    default_role: discord.Role,
) -> None:
    """
    Assert the base permissions for a voice channel to ensure proper operation.

    This ensures that:
    1. The default role can connect and use voice activation
    2. The bot has manage_channels and connect permissions
    3. The owner has connect permissions (channel management is via bot commands)

    Args:
        channel: The voice channel to update
        bot_member: The bot's member object
        owner_member: The channel owner's member object
        default_role: The default role for the guild (usually @everyone)
    """
    try:
        # Get existing overwrites (may include JTC-inherited permissions)
        overwrites = dict(channel.overwrites)

        # Merge base permissions for default role (@everyone).
        # Uses update() to preserve existing fields (e.g. speak=False from JTC)
        # while ensuring connect and use_voice_activation are always True.
        default_overwrite = overwrites.get(default_role, discord.PermissionOverwrite())
        default_overwrite.update(connect=True, use_voice_activation=True)
        overwrites[default_role] = default_overwrite

        # Merge base permissions for bot (needs manage_channels + connect)
        bot_overwrite = overwrites.get(bot_member, discord.PermissionOverwrite())
        bot_overwrite.update(manage_channels=True, connect=True)
        overwrites[bot_member] = bot_overwrite

        # Merge base permissions for owner (connect only — management via bot commands)
        owner_overwrite = overwrites.get(owner_member, discord.PermissionOverwrite())
        owner_overwrite.update(connect=True)
        overwrites[owner_member] = owner_overwrite

        # Remove overwrites for roles at or above the bot's top role.
        # Discord API rejects channel.edit(overwrites=...) if any target
        # role is >= the bot role in hierarchy.  We drop those entries so
        # the remaining (manageable) overwrites can still be applied.
        blocked_roles = _get_hierarchy_blocking_roles(
            overwrites,
            bot_member,
            default_role,
        )
        if blocked_roles:
            logger.debug(
                "Filtering %d role(s) above bot hierarchy for channel %s: %s",
                len(blocked_roles),
                channel.id,
                ", ".join(blocked_roles),
            )
            bot_top_role = bot_member.top_role
            overwrites = {
                target: ow
                for target, ow in overwrites.items()
                if not (
                    isinstance(target, discord.Role)
                    and target != default_role
                    and target >= bot_top_role
                )
            }

        # Apply the overwrites
        try:
            await channel.edit(overwrites=overwrites)
        except discord.Forbidden:
            logger.warning(
                "Skipping base permission update for channel %s due to missing permissions",
                channel.id,
            )
            return

        logger.debug("Base permissions asserted for channel %s", channel.id)
    except Exception:
        logger.exception(
            "Error asserting base permissions for channel %s",
            channel.id,
        )


async def enforce_permission_changes(
    channel: discord.VoiceChannel,
    bot: discord.Client,
    user_id: int,
    guild_id: int,
    jtc_channel_id: int,
) -> None:
    """
    Enforce all permission changes for a channel based on the database settings.

    This should be called after any permission change or owner transfer.

    Args:
        channel: The voice channel to update
        bot: The bot client
        user_id: The owner's user ID
        guild_id: The guild ID
        jtc_channel_id: The join-to-create channel ID
    """
    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.error("Could not find guild with ID %s", guild_id)
            return

        # Get the owner, bot member, and default role
        owner_member = guild.get_member(user_id)
        # Note: guild.me is the property for the bot's member in the guild
        bot_member = guild.me
        default_role = guild.default_role

        if not owner_member:
            logger.error(
                "Could not find owner member with ID %s in guild %s",
                user_id,
                guild_id,
            )
            return

        if not bot_member:
            logger.error("Could not find bot member in guild %s", guild_id)
            return

        # Assert base permissions
        await assert_base_permissions(channel, bot_member, owner_member, default_role)

        # Apply all other permission settings from the database
        await _apply_database_settings(
            channel, guild, user_id, guild_id, jtc_channel_id
        )

    except Exception:
        logger.exception(
            "Error enforcing permission changes for channel %s",
            channel.id,
        )


# FEATURE_CONFIG is imported from helpers.permissions_helper (single source of truth)


async def _apply_database_settings(
    channel: discord.VoiceChannel,
    guild: discord.Guild,
    user_id: int,
    guild_id: int,
    jtc_channel_id: int,
) -> None:
    """
    Apply all database-driven settings to the channel.

    This includes:
    - Permit/reject settings (connect permissions)
    - PTT settings (use_voice_activation)
    - Priority speaker settings
    - Soundboard settings
    - Lock state
    """
    try:
        # Get current overwrites to modify
        overwrites = dict(channel.overwrites)

        # Apply permit/reject settings
        await _apply_permit_reject_settings(
            overwrites, guild, user_id, guild_id, jtc_channel_id
        )

        # Apply voice feature settings (PTT, Priority Speaker, Soundboard)
        await _apply_voice_feature_settings(
            overwrites, guild, user_id, guild_id, jtc_channel_id
        )

        # Apply lock setting
        await _apply_lock_setting(overwrites, guild, user_id, guild_id, jtc_channel_id)

        bot_member = guild.me
        if bot_member is not None:
            blocked_roles = _get_hierarchy_blocking_roles(
                overwrites,
                bot_member,
                guild.default_role,
            )
            if blocked_roles:
                logger.warning(
                    "Skipping database permission update for channel %s due to role hierarchy: %s",
                    channel.id,
                    ", ".join(blocked_roles),
                )
                return

        # Apply all changes in one batch
        try:
            await channel.edit(overwrites=overwrites)
        except discord.Forbidden:
            logger.warning(
                "Skipping database permission update for channel %s due to missing permissions",
                channel.id,
            )
            return

        logger.debug("Applied database settings to channel %s", channel.id)

    except Exception:
        logger.exception(
            "Error applying database settings to channel %s",
            channel.id,
        )


async def _apply_permit_reject_settings(
    overwrites: dict,
    guild: discord.Guild,
    user_id: int,
    guild_id: int,
    jtc_channel_id: int,
) -> None:
    """Apply permit/reject settings from channel_permissions table."""
    permissions = await BaseRepository.fetch_all(
        """
        SELECT target_id, target_type, permission
        FROM channel_permissions
        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
        """,
        (user_id, guild_id, jtc_channel_id),
    )

    for target_id, target_type, permission in permissions:
        target = None

        if target_type == "user":
            target = guild.get_member(target_id)
        elif target_type == "role":
            target = guild.get_role(target_id)
        elif target_type == "everyone":
            target = guild.default_role

        if target:
            # Get or create overwrite for this target
            overwrite = overwrites.get(target, discord.PermissionOverwrite())

            # Apply permission
            if permission == "permit":
                overwrite.connect = True
            elif permission == "reject":
                overwrite.connect = False

            overwrites[target] = overwrite
            logger.debug("Applied %s for %s %s", permission, target_type, target_id)


async def _apply_voice_feature_settings(
    overwrites: dict,
    guild: discord.Guild,
    user_id: int,
    guild_id: int,
    jtc_channel_id: int,
) -> None:
    """Apply PTT, Priority Speaker, and Soundboard settings."""
    for feature_name, config in FEATURE_CONFIG.items():
        table_name = config["db_table"]
        column_name = config["db_column"]
        overwrite_property = config["overwrite_property"]
        inverted = config.get("inverted", False)

        settings = await BaseRepository.fetch_all(
            f"""
            SELECT target_id, target_type, {column_name}
            FROM {table_name}
            WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
            """,
            (user_id, guild_id, jtc_channel_id),
        )

        for target_id, target_type, enabled in settings:
            target = None

            if target_type == "user":
                target = guild.get_member(target_id)
            elif target_type == "role":
                target = guild.get_role(target_id)
            elif target_type == "everyone":
                target = guild.default_role

            if target:
                # Get or create overwrite for this target
                overwrite = overwrites.get(target, discord.PermissionOverwrite())

                # Apply the feature setting
                value = not enabled if inverted else enabled
                setattr(overwrite, overwrite_property, value)

                overwrites[target] = overwrite
                logger.debug(
                    "Applied %s=%s for %s %s",
                    feature_name,
                    enabled,
                    target_type,
                    target_id,
                )


async def _apply_lock_setting(
    overwrites: dict,
    guild: discord.Guild,
    user_id: int,
    guild_id: int,
    jtc_channel_id: int,
) -> None:
    """Apply lock setting from channel_settings table."""
    row = await BaseRepository.fetch_one(
        """
        SELECT lock FROM channel_settings
        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
        """,
        (user_id, guild_id, jtc_channel_id),
    )

    if row and row[0]:  # lock = 1 means locked
        # Lock the channel by denying connect to @everyone
        default_role = guild.default_role
        overwrite = overwrites.get(default_role, discord.PermissionOverwrite())
        overwrite.connect = False
        overwrites[default_role] = overwrite
        logger.debug("Applied lock setting to channel")
