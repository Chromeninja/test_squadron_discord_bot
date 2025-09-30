"""
Voice settings helper functions for managing and fetching voice channel settings.

This module provides utilities for fetching voice channel settings that can be
shared between different voice commands.
"""

from typing import Any

import discord

from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)


async def fetch_channel_settings(
    bot: discord.Client,
    interaction: discord.Interaction,
    target_user: discord.Member | None = None,
    allow_inactive: bool = True,
) -> dict[str, Any]:
    """
    Fetch channel settings for a user, either from active voice channel or saved settings.

    Args:
        bot: Discord bot client
        interaction: Discord interaction object
        target_user: Target user (defaults to interaction user for normal list command)
        allow_inactive: Whether to show saved settings even when user is not in a voice channel

    Returns:
        Dictionary containing:
        - 'settings': Dict of channel settings or None
        - 'active_channel': Active voice channel or None
        - 'is_active': Whether user is currently in a voice channel
        - 'jtc_channel_id': JTC channel ID if settings exist
        - 'embeds': List of embeds to display
    """
    guild_id = interaction.guild_id
    user = target_user or interaction.user

    result = {
        "settings": None,
        "active_channel": None,
        "is_active": False,
        "jtc_channel_id": None,
        "embeds": [],
    }

    try:
        # Check if user is in a voice channel
        if user.voice and user.voice.channel:
            result["active_channel"] = user.voice.channel
            result["is_active"] = True

            # Try to get settings for active channel
            # First check if this is a managed voice channel
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT jtc_channel_id FROM voice_channels
                    WHERE voice_channel_id = ? AND owner_id = ? AND is_active = 1
                """,
                    (user.voice.channel.id, user.id),
                )
                row = await cursor.fetchone()

                if row:
                    jtc_channel_id = row[0]
                    result["jtc_channel_id"] = jtc_channel_id

                    # Get settings for this active channel
                    settings = await _get_all_user_settings(
                        guild_id, jtc_channel_id, user.id
                    )
                    if settings:
                        result["settings"] = settings
                        embed = await _create_settings_embed(
                            user, settings, result["active_channel"], is_active=True
                        )
                        result["embeds"].append(embed)

        # If not active or allow_inactive is True, also check for saved settings
        if not result["is_active"] or allow_inactive:
            if target_user:
                # For admin_list: get all JTC channels for this user
                all_settings = await _get_all_user_jtc_settings(guild_id, user.id)
                for jtc_channel_id, settings in all_settings.items():
                    if settings:
                        embed = await _create_settings_embed(
                            user,
                            settings,
                            None,
                            is_active=False,
                            jtc_channel_id=jtc_channel_id,
                        )
                        result["embeds"].append(embed)
                        if not result["settings"]:  # Set the first one as primary
                            result["settings"] = settings
                            result["jtc_channel_id"] = jtc_channel_id
            else:
                # For user list: get saved settings using last used JTC for deterministic behavior
                last_used_jtc = await _get_last_used_jtc_channel(guild_id, user.id)
                if last_used_jtc:
                    # Load settings for last used JTC
                    settings = await _get_all_user_settings(
                        guild_id, last_used_jtc, user.id
                    )
                    if settings:
                        result["settings"] = settings
                        result["jtc_channel_id"] = last_used_jtc

                        embed = await _create_settings_embed(
                            user,
                            settings,
                            None,
                            is_active=False,
                            jtc_channel_id=last_used_jtc,
                        )
                        result["embeds"].append(embed)
                else:
                    # No last used JTC found, get available JTCs for selection
                    available_jtcs = await _get_available_jtc_channels(guild_id, user.id)
                    if available_jtcs:
                        # Create an informative embed prompting user to select a JTC
                        embed = discord.Embed(
                            title="🎙️ Multiple JTC Channels Found",
                            description=f"{user.display_name} has settings in multiple Join-to-Create channels. Please use a specific JTC channel or create/join a channel to set preference.",
                            color=discord.Color.orange()
                        )

                        jtc_list = []
                        for jtc_id in available_jtcs:
                            jtc_list.append(f"• JTC Channel ID: {jtc_id}")

                        embed.add_field(
                            name="Available JTC Channels",
                            value="\n".join(jtc_list),
                            inline=False
                        )
                        result["embeds"].append(embed)
                    # If no available JTCs, result stays empty (no settings)

        return result

    except Exception as e:
        logger.exception("Error fetching channel settings", exc_info=e)
        return result


async def _get_all_user_settings(
    guild_id: int, jtc_channel_id: int, user_id: int
) -> dict[str, Any]:
    """Get all settings for a user's channel in a specific JTC."""
    settings = {}

    try:
        async with Database.get_connection() as db:
            # Get basic channel settings
            cursor = await db.execute(
                """
                SELECT channel_name, user_limit, lock
                FROM channel_settings
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
                (guild_id, jtc_channel_id, user_id),
            )
            row = await cursor.fetchone()

            if row:
                channel_name, user_limit, lock = row
                settings.update(
                    {
                        "channel_name": channel_name,
                        "user_limit": user_limit,
                        "lock": bool(lock),
                    }
                )

            # Get permissions
            cursor = await db.execute(
                """
                SELECT target_id, target_type, permission
                FROM channel_permissions
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
                (guild_id, jtc_channel_id, user_id),
            )
            permissions = await cursor.fetchall()
            if permissions:
                settings["permissions"] = permissions

            # Get PTT settings
            cursor = await db.execute(
                """
                SELECT target_id, target_type, ptt_enabled
                FROM channel_ptt_settings
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
                (guild_id, jtc_channel_id, user_id),
            )
            ptt_settings = await cursor.fetchall()
            if ptt_settings:
                settings["ptt_settings"] = ptt_settings

            # Get priority speaker settings
            cursor = await db.execute(
                """
                SELECT target_id, target_type, priority_enabled
                FROM channel_priority_speaker_settings
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
                (guild_id, jtc_channel_id, user_id),
            )
            priority_settings = await cursor.fetchall()
            if priority_settings:
                settings["priority_settings"] = priority_settings

            # Get soundboard settings
            cursor = await db.execute(
                """
                SELECT target_id, target_type, soundboard_enabled
                FROM channel_soundboard_settings
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
                (guild_id, jtc_channel_id, user_id),
            )
            soundboard_settings = await cursor.fetchall()
            if soundboard_settings:
                settings["soundboard_settings"] = soundboard_settings

    except Exception as e:
        logger.exception("Error getting user settings", exc_info=e)

    return settings


async def _get_all_user_jtc_settings(
    guild_id: int, user_id: int
) -> dict[int, dict[str, Any]]:
    """Get all settings for a user across all JTC channels."""
    all_settings = {}

    try:
        async with Database.get_connection() as db:
            # Get all JTC channel IDs where this user has settings
            cursor = await db.execute(
                """
                SELECT DISTINCT jtc_channel_id
                FROM channel_settings
                WHERE guild_id = ? AND user_id = ?
            """,
                (guild_id, user_id),
            )
            jtc_rows = await cursor.fetchall()

            for (jtc_channel_id,) in jtc_rows:
                settings = await _get_all_user_settings(
                    guild_id, jtc_channel_id, user_id
                )
                if settings:
                    all_settings[jtc_channel_id] = settings

    except Exception as e:
        logger.exception("Error getting all user JTC settings", exc_info=e)

    return all_settings


async def _get_last_used_jtc_channel(guild_id: int, user_id: int) -> int | None:
    """Get the last used JTC channel for a user in a guild."""
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT last_used_jtc_channel_id
                FROM user_jtc_preferences
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.exception("Error getting last used JTC channel", exc_info=e)
        return None


async def _get_available_jtc_channels(guild_id: int, user_id: int) -> list[int]:
    """Get all JTC channels where a user has settings."""
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT DISTINCT jtc_channel_id
                FROM channel_settings
                WHERE guild_id = ? AND user_id = ?
                ORDER BY jtc_channel_id
                """,
                (guild_id, user_id),
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.exception("Error getting available JTC channels", exc_info=e)
        return []


async def update_last_used_jtc_channel(guild_id: int, user_id: int, jtc_channel_id: int) -> None:
    """Update the last used JTC channel for a user."""
    try:
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO user_jtc_preferences
                (guild_id, user_id, last_used_jtc_channel_id, updated_at)
                VALUES (?, ?, ?, strftime('%s','now'))
                """,
                (guild_id, user_id, jtc_channel_id),
            )
            await db.commit()
    except Exception as e:
        logger.exception("Error updating last used JTC channel", exc_info=e)


async def _create_settings_embed(
    user: discord.Member,
    settings: dict[str, Any],
    active_channel: discord.VoiceChannel | None = None,
    is_active: bool = False,
    jtc_channel_id: int | None = None,
) -> discord.Embed:
    """Create an embed showing channel settings."""

    if is_active and active_channel:
        title = "🎙️ Active Voice Channel Settings"
        description = f"Settings for {user.display_name}'s active channel: **{active_channel.name}**"
        color = discord.Color.green()
    else:
        title = "🎙️ Saved Voice Channel Settings"
        description = f"Saved settings for {user.display_name}"
        if jtc_channel_id:
            description += f" (JTC: {jtc_channel_id})"
        color = discord.Color.blue()

    embed = discord.Embed(title=title, description=description, color=color)

    # Basic settings
    basic_settings = []
    if settings.get("channel_name"):
        basic_settings.append(f"**Name:** {settings['channel_name']}")
    if settings.get("user_limit") is not None:
        limit = settings["user_limit"]
        limit_text = str(limit) if limit > 0 else "No limit"
        basic_settings.append(f"**User Limit:** {limit_text}")
    if settings.get("lock"):
        basic_settings.append(
            f"**Lock:** {'🔒 Locked' if settings['lock'] else '🔓 Unlocked'}"
        )

    if basic_settings:
        embed.add_field(
            name="Channel Settings", value="\n".join(basic_settings), inline=False
        )

    # Permission settings
    if settings.get("permissions"):
        perm_text = []
        for target_id, target_type, permission in settings["permissions"]:
            perm_text.append(f"**{target_type.title()} {target_id}:** {permission}")

        if perm_text:
            embed.add_field(
                name="Permission Overrides",
                value="\n".join(perm_text[:10]),  # Limit to prevent embed overflow
                inline=False,
            )

    # Voice features
    features = []
    if settings.get("ptt_settings"):
        ptt_count = len(settings["ptt_settings"])
        features.append(f"**PTT Settings:** {ptt_count} override(s)")
    if settings.get("priority_settings"):
        priority_count = len(settings["priority_settings"])
        features.append(f"**Priority Speaker:** {priority_count} override(s)")
    if settings.get("soundboard_settings"):
        soundboard_count = len(settings["soundboard_settings"])
        features.append(f"**Soundboard:** {soundboard_count} override(s)")

    if features:
        embed.add_field(name="Voice Features", value="\n".join(features), inline=False)

    embed.set_thumbnail(url=user.display_avatar.url)

    return embed
