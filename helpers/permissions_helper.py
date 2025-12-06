"""Permission utilities for voice-channel management and role validation.

Single canonical implementation providing (previous duplicates removed):
    - FEATURE_CONFIG
    - store_permit_reject_in_db
    - fetch_permit_reject_entries
    - apply_permissions_changes
    - reset_channel_permissions
    - update_channel_owner
    - apply_permit_reject_settings
    - resolve_role_ids_for_guild
    - app_command_check_configured_roles
Behavior and signatures preserved for existing call sites.
"""

import logging
from collections.abc import Iterable
from typing import Any, cast

import discord
from aiosqlite import Row

from helpers.discord_api import edit_channel
from services.db.database import Database

logger = logging.getLogger(__name__)

FEATURE_CONFIG = {
    "ptt": {
        "overwrite_property": "use_voice_activation",
        "db_table": "channel_ptt_settings",
        "db_column": "ptt_enabled",
        "inverted": True,
    },
    "priority_speaker": {
        "overwrite_property": "priority_speaker",
        "db_table": "channel_priority_speaker_settings",
        "db_column": "priority_enabled",
        "inverted": False,
    },
    "soundboard": {
        "overwrite_property": "use_soundboard",
        "db_table": "channel_soundboard_settings",
        "db_column": "soundboard_enabled",
        "inverted": False,
    },
}


async def store_permit_reject_in_db(
    user_id: int,
    target_id: int,
    target_type: str,
    action: str,
    guild_id=None,
    jtc_channel_id=None,
) -> None:
    """
    Store permit/reject settings in the database

    Args:
        user_id: The user ID who owns the channel
        target_id: The target user or role ID to apply permissions to
        target_type: The type of target ("user", "role", or "everyone")
        action: The permission action ("permit" or "reject")
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
    """
    if guild_id and jtc_channel_id:
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO channel_permissions
                (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, jtc_channel_id, user_id, target_id, target_type, action),
            )
            await db.commit()
    else:
        # Legacy mode for backward compatibility
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, target_id, target_type, action),
            )
            await db.commit()


async def fetch_permit_reject_entries(
    user_id: int, guild_id=None, jtc_channel_id=None
) -> Iterable[Row]:
    """
    Fetch all permit/reject entries for a user

    Args:
        user_id: The user ID to fetch entries for
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
    """
    if guild_id and jtc_channel_id:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT target_id, target_type, permission
                FROM channel_permissions
                WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (user_id, guild_id, jtc_channel_id),
            )
            return await cursor.fetchall()
    else:
        # Legacy mode for backward compatibility
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT target_id, target_type, permission FROM channel_permissions WHERE user_id = ?",
                (user_id,),
            )
            return await cursor.fetchall()


async def apply_permissions_changes(
    channel: discord.VoiceChannel, perm_settings: dict
) -> None:
    action = perm_settings.get("action")
    targets = perm_settings.get("targets", [])

    overwrites = channel.overwrites.copy()

    def _set_connect(target_obj, allow: bool) -> None:
        ow = overwrites.get(target_obj, discord.PermissionOverwrite())
        ow.connect = allow
        overwrites[target_obj] = ow

    if action in ("permit", "reject"):
        allow = action == "permit"
        for t in targets:
            ttype = t.get("type")
            tid = t.get("id")
            if ttype == "user":
                member = channel.guild.get_member(tid)
                if member:
                    _set_connect(member, allow)
            elif ttype == "role":
                role = channel.guild.get_role(tid)
                if role:
                    _set_connect(role, allow)
            elif ttype == "everyone":
                _set_connect(channel.guild.default_role, allow)
    elif action in ("lock", "unlock"):
        allow = action != "lock"
        for t in targets:
            ttype = t.get("type")
            tid = t.get("id")
            if ttype == "user":
                member = channel.guild.get_member(tid)
                if member:
                    _set_connect(member, allow)
            elif ttype == "role":
                role = channel.guild.get_role(tid)
                if role:
                    _set_connect(role, allow)
            elif ttype == "everyone":
                _set_connect(channel.guild.default_role, allow)
    else:
        logger.warning("Unknown permission action: %s", action)
        return

    # Ensure channel owner retains manage/connect
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1",
                (channel.id,),
            )
            row = await cursor.fetchone()
            if row:
                owner = channel.guild.get_member(row[0])
                if owner:
                    ow = overwrites.get(owner, discord.PermissionOverwrite())
                    ow.manage_channels = True
                    ow.connect = True
                    overwrites[owner] = ow
    except Exception as exc:
        logger.exception("Failed to ensure owner permissions: %s", exc)

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info("Applied permission '%s' to channel '%s'.", action, channel.name)
    except Exception as exc:
        logger.exception(
            "Failed to apply permission change to %s: %s", channel.name, exc
        )
        raise


async def reset_channel_permissions(
    channel: discord.VoiceChannel | discord.StageChannel,
) -> None:
    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            connect=True, use_voice_activation=True
        ),
        guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True),
    }
    await edit_channel(channel, overwrites=overwrites)
    logger.info("Reset permissions for channel '%s'.", channel.name)


async def update_channel_owner(
    channel: discord.VoiceChannel | discord.StageChannel,
    new_owner_id: int,
    previous_owner_id: int,
    guild_id=None,
    jtc_channel_id=None,
) -> None:
    """
    Update the owner of a voice channel in the database and permissions

    Args:
        channel: The voice channel to update
        new_owner_id: The ID of the new owner
        previous_owner_id: The ID of the previous owner
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
    """
    overwrites = channel.overwrites.copy()
    if prev := channel.guild.get_member(previous_owner_id):
        overwrites.pop(prev, None)
    new_owner = channel.guild.get_member(new_owner_id)
    if new_owner:
        ow = overwrites.get(new_owner, discord.PermissionOverwrite())
        ow.manage_channels = True
        ow.connect = True
        overwrites[new_owner] = ow

    await edit_channel(channel, overwrites=overwrites)
    logger.info(
        f"Updated channel owner for '{channel.name}' from {previous_owner_id} to {new_owner_id}."
    )

    # Update database record
    async with Database.get_connection() as db:
        if guild_id and jtc_channel_id:
            # Update with guild and JTC channel context
            await db.execute(
                """
                UPDATE voice_channels
                SET owner_id = ?
                WHERE voice_channel_id = ? AND guild_id = ? AND jtc_channel_id = ? AND is_active = 1
                """,
                (new_owner_id, channel.id, guild_id, jtc_channel_id),
            )
        else:
            # Legacy update for backward compatibility
            await db.execute(
                "UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
                (new_owner_id, channel.id),
            )
        await db.commit()


async def apply_permit_reject_settings(
    user_id: int, channel: discord.VoiceChannel
) -> None:
    entries = await fetch_permit_reject_entries(user_id)
    if not entries:
        return
    for target_id, target_type, permission in entries:
        try:
            await apply_permissions_changes(
                channel,
                {
                    "action": permission,
                    "targets": [{"type": target_type, "id": target_id}],
                },
            )
            logger.info(
                "Applied %s for %s (%s) on %s.",
                permission,
                target_id,
                target_type,
                channel.name,
            )
        except Exception:
            logger.exception(
                "Failed to apply stored permission %s for %s on %s.",
                permission,
                target_id,
                channel.name,
            )


def resolve_role_ids_for_guild(
    guild: discord.Guild, role_ids: Iterable[int | str]
) -> tuple[list[discord.Role], list[int]]:
    normalized_ids = cast(
        "list[int]",
        _normalize_role_ids(
            role_ids,
            guild_id=getattr(guild, "id", None),
            key="resolve_role_ids_for_guild",
            preserve_order=True,
        ),
    )

    resolved: list[discord.Role] = []
    missing: list[int] = []
    for rid in normalized_ids:
        role = guild.get_role(rid) if rid is not None else None
        if role:
            resolved.append(role)
        else:
            missing.append(rid)
    return resolved, missing


def get_role_display_name(
    guild: discord.Guild | None, role_id: int | str | None
) -> str:
    """Return a user-friendly role label, falling back to ID when missing."""

    if guild is None or role_id is None:
        return "Unknown role"

    normalized = _normalize_role_ids(
        [role_id],
        guild_id=getattr(guild, "id", None),
        key="get_role_display_name",
        preserve_order=True,
    )
    rid = normalized[0] if normalized else None

    if rid is None:
        return "Unknown role"

    role = guild.get_role(rid)
    if role:
        return f"@{role.name}"
    return f"Unknown role ({rid})"


PERMISSION_DENIED_MESSAGE = "You don't have permission to use this command."


# Role hierarchy levels for permission checking
from enum import IntEnum


class PermissionLevel(IntEnum):
    """Permission levels in hierarchical order (higher = more privilege)."""

    USER = 1
    STAFF = 2
    MODERATOR = 3
    DISCORD_MANAGER = 4
    BOT_ADMIN = 5
    BOT_OWNER = 6


def _resolve_guild(
    member: discord.Member, guild: discord.Guild | None
) -> discord.Guild | None:
    if guild is not None:
        return guild
    if isinstance(member, discord.Member):
        return member.guild
    return None


def _has_owner_or_discord_admin(
    bot, member: discord.Member, guild: discord.Guild
) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if bot.owner_id and member.id == bot.owner_id:
        return True
    if member.guild_permissions.administrator:
        return True
    return bool(guild.owner_id and member.id == guild.owner_id)


def _normalize_role_ids(
    values: Any,
    *,
    guild_id: int | None = None,
    key: str | None = None,
    preserve_order: bool = False,
) -> list[int] | set[int]:
    """Coerce role identifiers into ints, dropping invalid entries.

    Args:
        values: Raw value(s) returned from configuration or runtime.
        guild_id: Guild identifier for logging context.
        key: Config key for logging context.
        preserve_order: When True, returns a list preserving first-seen order.

    Returns:
        Either a list (if preserve_order) or set of normalized ints.
    """

    def _iter_values(item: Any) -> Iterable[Any]:
        if item is None:
            return []
        if isinstance(item, (str, bytes)):
            return [item]
        if isinstance(item, Iterable):
            flattened: list[Any] = []
            for value in item:
                flattened.extend(_iter_values(value))
            return flattened
        return [item]

    normalized_list: list[int] = []
    seen: set[int] = set()

    for raw in _iter_values(values):
        try:
            role_id = int(str(raw))
        except (TypeError, ValueError):
            if key:
                logger.warning(
                    "Invalid role id '%s' for %s in guild %s", raw, key, guild_id
                )
            continue
        if role_id < 0:
            if key:
                logger.warning(
                    "Ignoring negative role id '%s' for %s in guild %s",
                    raw,
                    key,
                    guild_id,
                )
            continue
        if role_id not in seen:
            seen.add(role_id)
            normalized_list.append(role_id)

    if preserve_order:
        return normalized_list
    return set(normalized_list)


async def _get_configured_role_ids(bot, guild_id: int, key: str) -> set[int]:
    config_service = getattr(getattr(bot, "services", None), "config", None)
    if not config_service:
        return set()
    try:
        roles = await config_service.get_guild_setting(guild_id, key, [])
        return cast(
            "set[int]",
            _normalize_role_ids(roles or [], guild_id=guild_id, key=key),
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Error fetching %s for guild %s: %s", key, guild_id, exc)
        return set()


def _member_role_ids(member: discord.Member) -> set[int]:
    if not isinstance(member, discord.Member):
        return set()
    return {role.id for role in getattr(member, "roles", [])}


async def get_permission_level(
    bot,
    member: discord.Member,
    guild: discord.Guild | None = None,
) -> PermissionLevel:
    """Determine the highest permission level for a member.

    Checks in hierarchy order:
    1. Bot owner (global)
    2. Guild owner / Discord administrator
    3. Bot admin role
    4. Discord manager role
    5. Moderator role
    6. Staff role
    7. Regular user (default)

    Args:
        bot: Bot instance with owner_id and services
        member: Discord member to check
        guild: Guild context (optional, derived from member if not provided)

    Returns:
        PermissionLevel enum value representing highest privilege
    """
    if not isinstance(member, discord.Member):
        return PermissionLevel.USER

    guild = _resolve_guild(member, guild)
    if guild is None:
        return PermissionLevel.USER

    # Check bot owner (highest privilege)
    if bot.owner_id and member.id == bot.owner_id:
        return PermissionLevel.BOT_OWNER

    # Check guild owner or Discord administrator (bot_admin equivalent)
    if member.guild_permissions.administrator or (
        guild.owner_id and member.id == guild.owner_id
    ):
        return PermissionLevel.BOT_ADMIN

    # Get user's role IDs
    user_role_ids = _member_role_ids(member)

    # Check configured role lists in hierarchy order
    bot_admin_ids = await _get_configured_role_ids(bot, guild.id, "roles.bot_admins")
    if user_role_ids & bot_admin_ids:
        return PermissionLevel.BOT_ADMIN

    discord_manager_ids = await _get_configured_role_ids(
        bot, guild.id, "roles.discord_managers"
    )
    if user_role_ids & discord_manager_ids:
        return PermissionLevel.DISCORD_MANAGER

    # Check moderators
    moderator_ids = await _get_configured_role_ids(bot, guild.id, "roles.moderators")
    if user_role_ids & moderator_ids:
        return PermissionLevel.MODERATOR

    staff_ids = await _get_configured_role_ids(bot, guild.id, "roles.staff")
    if user_role_ids & staff_ids:
        return PermissionLevel.STAFF

    return PermissionLevel.USER


async def is_bot_owner(
    bot,
    member: discord.Member,
    guild: discord.Guild | None = None,
) -> bool:
    """Check if user is the bot owner."""
    level = await get_permission_level(bot, member, guild)
    return level >= PermissionLevel.BOT_OWNER


async def is_bot_admin(
    bot,
    member: discord.Member,
    guild: discord.Guild | None = None,
) -> bool:
    """Check if user has bot admin privileges or higher."""
    level = await get_permission_level(bot, member, guild)
    return level >= PermissionLevel.BOT_ADMIN


async def is_discord_manager(
    bot,
    member: discord.Member,
    guild: discord.Guild | None = None,
) -> bool:
    """Check if user has discord manager privileges or higher."""
    level = await get_permission_level(bot, member, guild)
    return level >= PermissionLevel.DISCORD_MANAGER


async def is_moderator(
    bot,
    member: discord.Member,
    guild: discord.Guild | None = None,
) -> bool:
    """Check if user has moderator privileges or higher."""
    level = await get_permission_level(bot, member, guild)
    return level >= PermissionLevel.MODERATOR


async def is_staff(
    bot,
    member: discord.Member,
    guild: discord.Guild | None = None,
) -> bool:
    """Check if user has staff privileges or higher."""
    level = await get_permission_level(bot, member, guild)
    return level >= PermissionLevel.STAFF


def app_command_check_configured_roles(role_ids: Iterable[int]) -> Any:
    from discord import app_commands

    def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            raise app_commands.CheckFailure("This command can only be used in a guild.")
        resolved, _ = resolve_role_ids_for_guild(guild, role_ids)
        if not resolved:
            raise app_commands.CheckFailure(
                "Server missing configured admin/moderator roles."
            )
        return True

    return app_commands.check(predicate)


__all__ = [
    "FEATURE_CONFIG",
    "PERMISSION_DENIED_MESSAGE",
    "PermissionLevel",
    "app_command_check_configured_roles",
    "apply_permissions_changes",
    "apply_permit_reject_settings",
    "fetch_permit_reject_entries",
    "get_permission_level",
    "get_role_display_name",
    "is_bot_admin",
    "is_bot_owner",
    "is_discord_manager",
    "is_moderator",
    "is_staff",
    "reset_channel_permissions",
    "resolve_role_ids_for_guild",
    "store_permit_reject_in_db",
    "update_channel_owner",
]
