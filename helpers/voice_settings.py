"""
Voice settings helper functions for managing and fetching voice channel settings.

This module provides utilities for fetching voice channel settings that can be
shared between different voice commands.

Note: Database imports are done lazily inside functions to avoid circular imports
through services/__init__.py -> VoiceService -> voice_settings.
"""

from typing import TYPE_CHECKING, Any

import discord

from utils.logging import get_logger

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot

logger = get_logger(__name__)


VOICE_SETTINGS_FEATURE_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("permissions", "channel_permissions", "permission"),
    ("ptt_settings", "channel_ptt_settings", "ptt_enabled"),
    (
        "priority_settings",
        "channel_priority_speaker_settings",
        "priority_enabled",
    ),
    (
        "soundboard_settings",
        "channel_soundboard_settings",
        "soundboard_enabled",
    ),
)


async def resolve_target_names(
    guild: discord.Guild,
    snapshot: "VoiceSettingsSnapshot",
) -> None:
    """
    Resolve target names in a VoiceSettingsSnapshot.

    Annotates all TargetEntry objects (permissions, PTT, priority, soundboard)
    with resolved names and metadata flags:
    - target_name: Display name for the target
    - is_everyone: True if target is @everyone
    - unknown_role: True if target is a role that no longer exists

    This replaces all duplicated name resolution logic across commands and API.

    Args:
        guild: Discord guild for name resolution
        snapshot: VoiceSettingsSnapshot to annotate in-place
    """

    def resolve_single_target(
        target_id: str, target_type: str
    ) -> tuple[str | None, bool, bool]:
        """Resolve a single target to (name, is_everyone, unknown_role)."""
        if target_type == "user":
            # Check for @everyone (target_id == guild_id as string)
            if target_id == str(guild.id) or target_id == "0":
                return ("@everyone", True, False)

            # Regular user
            try:
                member = guild.get_member(int(target_id))
                if member:
                    return (member.display_name, False, False)
            except (ValueError, AttributeError):
                pass
            return (f"Unknown User ({target_id})", False, False)

        elif target_type == "role":
            # Check for @everyone (target_id == guild_id)
            if target_id == str(guild.id):
                return ("@everyone", True, False)

            # Regular role
            try:
                role = guild.get_role(int(target_id))
                if role:
                    return (f"@{role.name}", False, False)
            except (ValueError, AttributeError):
                pass
            return (None, False, True)  # Unknown role

        return (str(target_id), False, False)

    # Resolve all target entries
    for perm in snapshot.permissions:
        perm.target_name, perm.is_everyone, perm.unknown_role = resolve_single_target(
            perm.target_id, perm.target_type
        )

    for ptt in snapshot.ptt_settings:
        ptt.target_name, ptt.is_everyone, ptt.unknown_role = resolve_single_target(
            ptt.target_id, ptt.target_type
        )

    for priority in snapshot.priority_speaker_settings:
        priority.target_name, priority.is_everyone, priority.unknown_role = (
            resolve_single_target(priority.target_id, priority.target_type)
        )

    for soundboard in snapshot.soundboard_settings:
        soundboard.target_name, soundboard.is_everyone, soundboard.unknown_role = (
            resolve_single_target(soundboard.target_id, soundboard.target_type)
        )


async def get_voice_settings_snapshots(
    guild_id: int, user_id: int
) -> list["VoiceSettingsSnapshot"]:
    """Build VoiceSettingsSnapshot objects for all JTC channels a user has settings in.

    Returns snapshots with unresolved target names (IDs only). Name resolution can be
    applied by callers (e.g., Discord bot using resolve_target_names or API layer
    using guild role/member lookups).
    """

    from utils.types import (
        PermissionOverride,
        PrioritySpeakerSetting,
        PTTSetting,
        SoundboardSetting,
        VoiceSettingsSnapshot,
    )

    snapshots: list[VoiceSettingsSnapshot] = []

    all_settings = await _get_all_user_jtc_settings(guild_id, user_id)

    for jtc_channel_id, settings in all_settings.items():
        if not settings:
            continue

        permissions = [
            PermissionOverride(
                target_id=str(target_id),
                target_type=target_type,
                permission=permission,
            )
            for target_id, target_type, permission in settings.get("permissions", [])
        ]

        ptt_settings = [
            PTTSetting(
                target_id=str(target_id),
                target_type=target_type,
                ptt_enabled=bool(ptt_enabled),
            )
            for target_id, target_type, ptt_enabled in settings.get("ptt_settings", [])
        ]

        priority_settings = [
            PrioritySpeakerSetting(
                target_id=str(target_id),
                target_type=target_type,
                priority_enabled=bool(priority_enabled),
            )
            for target_id, target_type, priority_enabled in settings.get(
                "priority_settings", []
            )
        ]

        soundboard_settings = [
            SoundboardSetting(
                target_id=str(target_id),
                target_type=target_type,
                soundboard_enabled=bool(soundboard_enabled),
            )
            for target_id, target_type, soundboard_enabled in settings.get(
                "soundboard_settings", []
            )
        ]

        snapshots.append(
            VoiceSettingsSnapshot(
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
                owner_id=user_id,
                voice_channel_id=None,
                channel_name=settings.get("channel_name"),
                user_limit=settings.get("user_limit"),
                is_locked=bool(settings.get("lock", False)),
                permissions=permissions,
                ptt_settings=ptt_settings,
                priority_speaker_settings=priority_settings,
                soundboard_settings=soundboard_settings,
            )
        )

    return snapshots


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
        # Check if user is in a voice channel (only Members have voice state)
        if isinstance(user, discord.Member) and user.voice and user.voice.channel:
            result["active_channel"] = user.voice.channel
            result["is_active"] = True

            # Try to get settings for active channel
            # First check if this is a managed voice channel
            from services.db.repository import BaseRepository

            row = await BaseRepository.fetch_one(
                """
                SELECT jtc_channel_id FROM voice_channels
                WHERE voice_channel_id = ? AND owner_id = ? AND is_active = 1
                """,
                (user.voice.channel.id, user.id),
            )

            if row:
                jtc_channel_id = row[0]
                result["jtc_channel_id"] = jtc_channel_id

                # Get settings for this active channel
                if guild_id is not None:
                    settings = await _get_all_user_settings(
                        guild_id, jtc_channel_id, user.id
                    )
                    if settings:
                        result["settings"] = settings
                        if interaction.guild and isinstance(user, discord.Member):
                            # Type narrow active_channel to VoiceChannel
                            active_chan = result["active_channel"]
                            voice_chan = (
                                active_chan
                                if isinstance(active_chan, discord.VoiceChannel)
                                else None
                            )
                            embed = await _create_settings_embed(
                                user,
                                settings,
                                interaction.guild,
                                voice_chan,
                                is_active=True,
                            )
                            result["embeds"].append(embed)

        active_jtc_channel_id = result["jtc_channel_id"]

        if target_user and allow_inactive and guild_id is not None:
            # Admin list should surface stored settings across JTCs, but skip the
            # currently active JTC because it is already represented by the active embed.
            all_settings = await _get_all_user_jtc_settings(guild_id, user.id)
            for jtc_channel_id, settings in all_settings.items():
                if jtc_channel_id == active_jtc_channel_id:
                    continue

                if settings and interaction.guild and isinstance(user, discord.Member):
                    embed = await _create_settings_embed(
                        user,
                        settings,
                        interaction.guild,
                        None,
                        is_active=False,
                        jtc_channel_id=jtc_channel_id,
                    )
                    result["embeds"].append(embed)
                    if not result["settings"]:  # Set the first one as primary
                        result["settings"] = settings
                        result["jtc_channel_id"] = jtc_channel_id

        elif result["settings"] is None and allow_inactive and guild_id is not None:
            # For normal user list flows, saved settings are a fallback when the
            # current voice state does not resolve to managed channel settings.
            available_jtcs: list[int] = []
            last_used_jtc = await _get_last_used_jtc_channel(guild_id, user.id)

            if last_used_jtc:
                settings = await _get_all_user_settings(guild_id, last_used_jtc, user.id)
                if settings and interaction.guild and isinstance(user, discord.Member):
                    result["settings"] = settings
                    result["jtc_channel_id"] = last_used_jtc

                    embed = await _create_settings_embed(
                        user,
                        settings,
                        interaction.guild,
                        None,
                        is_active=False,
                        jtc_channel_id=last_used_jtc,
                    )
                    result["embeds"].append(embed)
                else:
                    available_jtcs = await _get_available_jtc_channels(guild_id, user.id)
            else:
                available_jtcs = await _get_available_jtc_channels(guild_id, user.id)

            if last_used_jtc and available_jtcs:
                available_jtcs = [
                    jtc_id for jtc_id in available_jtcs if jtc_id != last_used_jtc
                ]

            if available_jtcs:
                embed = discord.Embed(
                    title="🎙️ Multiple JTC Channels Found",
                    description=f"{user.display_name} has settings in multiple Join-to-Create channels. Please use a specific JTC channel or create/join a channel to set preference.",
                    color=discord.Color.orange(),
                )

                jtc_list = []
                for jtc_id in available_jtcs:
                    jtc_list.append(f"• JTC Channel ID: {jtc_id}")

                embed.add_field(
                    name="Available JTC Channels",
                    value="\n".join(jtc_list),
                    inline=False,
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
    all_settings = await _fetch_user_settings_map(
        guild_id,
        user_id,
        jtc_channel_id=jtc_channel_id,
    )
    return all_settings.get(jtc_channel_id, {})


async def _get_all_user_jtc_settings(
    guild_id: int, user_id: int
) -> dict[int, dict[str, Any]]:
    """Get all settings for a user across all JTC channels."""
    return await _fetch_user_settings_map(guild_id, user_id)


def _build_feature_union_query(where_clause: str) -> str:
    """Build the UNION ALL query used to fetch all per-target voice settings."""
    select_clauses = [
        (
            "SELECT jtc_channel_id, "
            f"'{setting_group}' AS setting_group, "
            "target_id, "
            "target_type, "
            f"{value_column} AS setting_value "
            f"FROM {table_name} "
            f"WHERE {where_clause}"
        )
        for setting_group, table_name, value_column in VOICE_SETTINGS_FEATURE_SOURCES
    ]
    return "\nUNION ALL\n".join(select_clauses) + "\nORDER BY jtc_channel_id"


def _build_user_settings_scope(
    guild_id: int,
    user_id: int,
    jtc_channel_id: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """Build a shared WHERE clause and parameters for voice settings queries."""
    where_clause = "guild_id = ? AND user_id = ?"
    params: tuple[Any, ...] = (guild_id, user_id)
    if jtc_channel_id is not None:
        where_clause += " AND jtc_channel_id = ?"
        params += (jtc_channel_id,)
    return where_clause, params


async def _fetch_user_settings_map(
    guild_id: int,
    user_id: int,
    jtc_channel_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    """Fetch voice settings grouped by JTC channel with minimal query fan-out."""
    from services.db.repository import BaseRepository

    settings_map: dict[int, dict[str, Any]] = {}

    where_clause, params = _build_user_settings_scope(
        guild_id,
        user_id,
        jtc_channel_id,
    )

    try:
        async with BaseRepository.transaction() as db:
            basic_cursor = await db.execute(
                f"""
                SELECT jtc_channel_id, channel_name, user_limit, lock
                FROM channel_settings
                WHERE {where_clause}
                ORDER BY jtc_channel_id
                """,
                params,
            )
            basic_rows = await basic_cursor.fetchall()

            for row in basic_rows:
                current_jtc_channel_id, channel_name, user_limit, lock = row
                settings_map[current_jtc_channel_id] = {
                    "channel_name": channel_name,
                    "user_limit": user_limit,
                    "lock": bool(lock),
                }

            union_query = _build_feature_union_query(where_clause)
            union_params = params * len(VOICE_SETTINGS_FEATURE_SOURCES)
            feature_cursor = await db.execute(union_query, union_params)
            feature_rows = await feature_cursor.fetchall()

            for row in feature_rows:
                current_jtc_channel_id, setting_group, target_id, target_type, value = row
                if current_jtc_channel_id not in settings_map:
                    if jtc_channel_id is None:
                        continue
                    settings_map[current_jtc_channel_id] = {}

                settings_map.setdefault(current_jtc_channel_id, {}).setdefault(
                    setting_group, []
                ).append((target_id, target_type, value))

    except Exception as e:
        logger.exception("Error getting user settings", exc_info=e)

    return settings_map


async def _get_last_used_jtc_channel(guild_id: int, user_id: int) -> int | None:
    """Get the last used JTC channel for a user in a guild."""
    # Lazy import to avoid circular dependency
    from services.db.repository import BaseRepository

    try:
        row = await BaseRepository.fetch_one(
            """
            SELECT last_used_jtc_channel_id
            FROM user_jtc_preferences
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        return row[0] if row else None
    except Exception as e:
        logger.exception("Error getting last used JTC channel", exc_info=e)
        return None


async def _get_available_jtc_channels(guild_id: int, user_id: int) -> list[int]:
    """Get all JTC channels where a user has settings."""
    # Lazy import to avoid circular dependency
    from services.db.repository import BaseRepository

    try:
        rows = await BaseRepository.fetch_all(
            """
            SELECT DISTINCT jtc_channel_id
            FROM channel_settings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY jtc_channel_id
            """,
            (guild_id, user_id),
        )
        return [row[0] for row in rows]
    except Exception as e:
        logger.exception("Error getting available JTC channels", exc_info=e)
        return []


async def update_last_used_jtc_channel(
    guild_id: int, user_id: int, jtc_channel_id: int
) -> None:
    """Update the last used JTC channel for a user."""
    # Lazy import to avoid circular dependency
    from services.db.repository import BaseRepository

    try:
        await BaseRepository.execute(
            """
            INSERT OR REPLACE INTO user_jtc_preferences
            (guild_id, user_id, last_used_jtc_channel_id, updated_at)
            VALUES (?, ?, ?, strftime('%s','now'))
            """,
            (guild_id, user_id, jtc_channel_id),
        )
    except Exception as e:
        logger.exception("Error updating last used JTC channel", exc_info=e)


def _resolve_target_name(
    guild: discord.Guild,
    target_id: int,
    target_type: str,
) -> str:
    """Resolve a target ID to a display name."""
    if target_type == "user":
        member = guild.get_member(target_id)
        if member:
            return member.display_name
        return f"Unknown User ({target_id})"
    elif target_type == "role":
        # Check for @everyone
        if target_id == guild.id:
            return "@everyone"
        role = guild.get_role(target_id)
        if role:
            return f"@{role.name}"
        return f"Unknown Role ({target_id})"
    return str(target_id)


async def _create_settings_embed(
    user: discord.Member,
    settings: dict[str, Any],
    guild: discord.Guild,
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
    if "lock" in settings:
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
            target_name = _resolve_target_name(guild, target_id, target_type)
            emoji = "✅" if permission == "permit" else "❌"
            perm_text.append(f"{emoji} **{target_name}:** {permission}")

        if perm_text:
            embed.add_field(
                name="Permission Overrides",
                value="\n".join(perm_text[:10]),  # Limit to prevent embed overflow
                inline=False,
            )

    # Voice features with detailed target names
    if settings.get("ptt_settings"):
        ptt_text = []
        for target_id, target_type, enabled in settings["ptt_settings"]:
            target_name = _resolve_target_name(guild, target_id, target_type)
            status = "🔇 Required" if enabled else "🔊 Disabled"
            ptt_text.append(f"{status} for **{target_name}**")
        if ptt_text:
            embed.add_field(
                name="🎤 Push-to-Talk Overrides",
                value="\n".join(ptt_text[:10]),
                inline=False,
            )

    if settings.get("priority_settings"):
        priority_text = []
        for target_id, target_type, enabled in settings["priority_settings"]:
            target_name = _resolve_target_name(guild, target_id, target_type)
            status = "✅ Enabled" if enabled else "❌ Disabled"
            priority_text.append(f"{status} for **{target_name}**")
        if priority_text:
            embed.add_field(
                name="📢 Priority Speaker Overrides",
                value="\n".join(priority_text[:10]),
                inline=False,
            )

    if settings.get("soundboard_settings"):
        soundboard_text = []
        for target_id, target_type, enabled in settings["soundboard_settings"]:
            target_name = _resolve_target_name(guild, target_id, target_type)
            status = "✅ Enabled" if enabled else "❌ Disabled"
            soundboard_text.append(f"{status} for **{target_name}**")
        if soundboard_text:
            embed.add_field(
                name="🔊 Soundboard Overrides",
                value="\n".join(soundboard_text[:10]),
                inline=False,
            )

    features = []

    if features:
        embed.add_field(name="Voice Features", value="\n".join(features), inline=False)

    embed.set_thumbnail(url=user.display_avatar.url)

    return embed
