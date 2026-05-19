"""
Voice Settings Embed Builder — Discord embed for voice channel settings UI.

Extracted from helpers/embeds.py to keep file sizes manageable.
Import from helpers.embeds for backward compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord  # type: ignore[import-not-found]

from helpers.permissions_helper import get_role_display_name
from utils.logging import get_logger

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot

logger = get_logger(__name__)


def build_voice_settings_ui(
    snapshot: VoiceSettingsSnapshot,
    user: discord.Member,
    active_channel: discord.VoiceChannel | None = None,
) -> discord.Embed:
    """
    Build a Discord embed showing voice channel settings from a snapshot.

    This is the unified UI renderer used by:
    - /voice list command
    - /voice admin_list command
    - Dashboard preview (converted to API response)

    Args:
        snapshot: VoiceSettingsSnapshot with resolved target names
        user: Discord member who owns the settings
        active_channel: Optional active voice channel

    Returns:
        Discord embed with formatted settings
    """

    # Determine if this is an active channel or saved settings
    is_active = snapshot.is_active and active_channel is not None

    if is_active and active_channel:
        title = "🎙️ Active Voice Channel Settings"
        description = f"Settings for {user.display_name}'s active channel: **{active_channel.name}**"
        color = discord.Color.green()
    else:
        title = "🎙️ Saved Voice Channel Settings"
        description = f"Saved settings for {user.display_name}"
        if snapshot.jtc_channel_id:
            description += f" (JTC: {snapshot.jtc_channel_id})"
        color = discord.Color.blue()

    embed = discord.Embed(title=title, description=description, color=color)

    # Basic settings section
    basic_settings = []
    if snapshot.channel_name:
        basic_settings.append(f"**Name:** {snapshot.channel_name}")
    if snapshot.user_limit is not None:
        limit_text = str(snapshot.user_limit) if snapshot.user_limit > 0 else "No limit"
        basic_settings.append(f"**User Limit:** {limit_text}")
    if snapshot.is_locked:
        basic_settings.append(
            f"**Lock:** {'🔒 Locked' if snapshot.is_locked else '🔓 Unlocked'}"
        )

    if basic_settings:
        embed.add_field(
            name="Channel Settings",
            value="\n".join(basic_settings),
            inline=False,
        )

    # Permission overrides section
    if snapshot.permissions:
        perm_text = []
        for perm in snapshot.permissions[:10]:  # Limit to prevent embed overflow
            emoji = "✅" if perm.permission == "permit" else "❌"
            target_display = perm.target_name
            if not target_display and perm.target_type == "role":
                target_display = get_role_display_name(user.guild, perm.target_id)
            if not target_display:
                target_display = f"Unknown ({perm.target_id})"
            perm_text.append(f"{emoji} **{target_display}:** {perm.permission}")

        if perm_text:
            embed.add_field(
                name="Permission Overrides",
                value="\n".join(perm_text),
                inline=False,
            )

    # Push-to-Talk section
    if snapshot.ptt_settings:
        ptt_text = []
        for ptt in snapshot.ptt_settings[:10]:
            status = "🔇 Required" if ptt.ptt_enabled else "🔊 Disabled"
            target_display = ptt.target_name
            if not target_display and ptt.target_type == "role":
                target_display = get_role_display_name(user.guild, ptt.target_id)
            if not target_display:
                target_display = f"Unknown ({ptt.target_id})"
            ptt_text.append(f"{status} for **{target_display}**")

        if ptt_text:
            embed.add_field(
                name="🎤 Push-to-Talk Overrides",
                value="\n".join(ptt_text),
                inline=False,
            )

    # Priority Speaker section
    if snapshot.priority_speaker_settings:
        priority_text = []
        for priority in snapshot.priority_speaker_settings[:10]:
            status = "✅ Enabled" if priority.priority_enabled else "❌ Disabled"
            target_display = priority.target_name
            if not target_display and priority.target_type == "role":
                target_display = get_role_display_name(user.guild, priority.target_id)
            if not target_display:
                target_display = f"Unknown ({priority.target_id})"
            priority_text.append(f"{status} for **{target_display}**")

        if priority_text:
            embed.add_field(
                name="📢 Priority Speaker Overrides",
                value="\n".join(priority_text),
                inline=False,
            )

    # Soundboard section
    if snapshot.soundboard_settings:
        soundboard_text = []
        for soundboard in snapshot.soundboard_settings[:10]:
            status = "✅ Enabled" if soundboard.soundboard_enabled else "❌ Disabled"
            target_display = soundboard.target_name
            if not target_display and soundboard.target_type == "role":
                target_display = get_role_display_name(user.guild, soundboard.target_id)
            if not target_display:
                target_display = f"Unknown ({soundboard.target_id})"
            soundboard_text.append(f"{status} for **{target_display}**")

        if soundboard_text:
            embed.add_field(
                name="🔊 Soundboard Overrides",
                value="\n".join(soundboard_text),
                inline=False,
            )

    embed.set_thumbnail(url=user.display_avatar.url)

    return embed
