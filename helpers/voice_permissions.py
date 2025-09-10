# helpers/voice_permissions.py

"""
Utilities for managing voice channel permissions.

This module provides functions for asserting and enforcing permissions
on user-created voice channels.
"""

import discord

from helpers.logger import get_logger

logger = get_logger(__name__)


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
    3. The owner has manage_channels and connect permissions

    Args:
        channel: The voice channel to update
        bot_member: The bot's member object
        owner_member: The channel owner's member object
        default_role: The default role for the guild (usually @everyone)
    """
    try:
        # Set up overwrites for default role (everyone)
        default_overwrite = discord.PermissionOverwrite(
            connect=True, use_voice_activation=True
        )

        # Set up overwrites for bot
        bot_overwrite = discord.PermissionOverwrite(manage_channels=True, connect=True)

        # Set up overwrites for owner
        owner_overwrite = discord.PermissionOverwrite(
            manage_channels=True, connect=True
        )

        # Get existing overwrites
        overwrites = dict(channel.overwrites)

        # Update the overwrites
        overwrites[default_role] = default_overwrite
        overwrites[bot_member] = bot_overwrite
        overwrites[owner_member] = owner_overwrite

        # Apply the overwrites
        await channel.edit(overwrites=overwrites)
        logger.debug(f"Base permissions asserted for channel {channel.id}")
    except Exception as e:
        logger.exception(f"Error asserting base permissions for channel {channel.id}: {e}")


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
            logger.error(f"Could not find guild with ID {guild_id}")
            return

        # Get the owner, bot member, and default role
        owner_member = guild.get_member(user_id)
        # Note: guild.me is the property for the bot's member in the guild
        bot_member = guild.me
        default_role = guild.default_role

        if not owner_member:
            logger.error(
                f"Could not find owner member with ID {user_id} in guild {guild_id}"
            )
            return

        if not bot_member:
            logger.error(f"Could not find bot member in guild {guild_id}")
            return

        # Assert base permissions
        await assert_base_permissions(channel, bot_member, owner_member, default_role)

        # TODO: Apply all other permission settings from the database
        # This would be added in a future implementation to apply PTT,
        # Priority Speaker, Soundboard, and permit/reject settings
    except Exception as e:
        logger.exception(
            f"Error enforcing permission changes for channel {channel.id}: {e}"
        )
