"""Permission utilities: role resolution and small app-command checks."""

import discord
from typing import Iterable, List, Tuple
from helpers.database import Database
from helpers.logger import get_logger
from helpers.discord_api import edit_channel

logger = get_logger(__name__)

FEATURE_CONFIG = {
    "ptt": {"overwrite_property": "use_voice_activation", "db_table": "channel_ptt_settings", "db_column": "ptt_enabled", "inverted": True},
    "priority_speaker": {"overwrite_property": "priority_speaker", "db_table": "channel_priority_speaker_settings", "db_column": "priority_enabled", "inverted": False},
    "soundboard": {"overwrite_property": "use_soundboard", "db_table": "channel_soundboard_settings", "db_column": "soundboard_enabled", "inverted": False},
}


async def store_permit_reject_in_db(user_id: int, target_id: int, target_type: str, action: str):
    """Store a permit/reject entry in the DB."""
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id, target_type, action),
        )
        await db.commit()


async def fetch_permit_reject_entries(user_id: int):
    """Return saved permit/reject entries for a user."""
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT target_id, target_type, permission FROM channel_permissions WHERE user_id = ?",
            (user_id,),
        )
        return await cursor.fetchall()


async def apply_permissions_changes(channel: discord.VoiceChannel, perm_settings: dict):
    """Apply basic connect permission changes (permit/reject/lock/unlock)."""
    action = perm_settings.get("action")
    targets = perm_settings.get("targets", [])

    overwrites = channel.overwrites.copy()

    def _set_connect(target_obj, allow: bool):
        ow = overwrites.get(target_obj, discord.PermissionOverwrite())
        ow.connect = allow
        overwrites[target_obj] = ow

    if action in ("permit", "reject"):
        allow = action == "permit"
        for t in targets:
            if t.get("type") == "user":
                member = channel.guild.get_member(t.get("id"))
                if member:
                    _set_connect(member, allow)
            elif t.get("type") == "role":
                role = channel.guild.get_role(t.get("id"))
                if role:
                    _set_connect(role, allow)
            elif t.get("type") == "everyone":
                _set_connect(channel.guild.default_role, allow)
    elif action in ("lock", "unlock"):
        allow = action != "lock"
        for t in targets:
            if t.get("type") == "user":
                member = channel.guild.get_member(t.get("id"))
                if member:
                    _set_connect(member, allow)
            elif t.get("type") == "role":
                role = channel.guild.get_role(t.get("id"))
                if role:
                    _set_connect(role, allow)
            elif t.get("type") == "everyone":
                _set_connect(channel.guild.default_role, allow)
    else:
        logger.warning(f"Unknown action: {action}")
        return

    # Ensure owner retains manage and connect
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?", (channel.id,))
            row = await cursor.fetchone()
            if row:
                owner = channel.guild.get_member(row[0])
                if owner:
                    ow = overwrites.get(owner, discord.PermissionOverwrite())
                    ow.manage_channels = True
                    ow.connect = True
                    overwrites[owner] = ow
    except Exception as e:
        logger.error(f"Failed to set owner permissions: {e}")

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Applied permission '{action}' to channel '{channel.name}'.")
    except Exception as e:
        logger.error(f"Failed to apply permission '{action}' to channel '{channel.name}': {e}")
        raise


async def reset_channel_permissions(channel: discord.VoiceChannel):
    """Reset a voice channel to default overwrites."""
    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=True, use_voice_activation=True),
        guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True),
    }
    await edit_channel(channel, overwrites=overwrites)
    logger.info(f"Reset permissions for channel '{channel.name}' to default.")


async def update_channel_owner(channel: discord.VoiceChannel, new_owner_id: int, previous_owner_id: int):
    """Update the owner overwrite for a channel."""
    overwrites = channel.overwrites.copy()
    if prev := channel.guild.get_member(previous_owner_id):
        overwrites.pop(prev, None)
    new_owner = channel.guild.get_member(new_owner_id)
    if new_owner:
        overwrites[new_owner] = discord.PermissionOverwrite(manage_channels=True, connect=True)
    await edit_channel(channel, overwrites=overwrites)
    logger.info(f"Updated channel owner to '{new_owner.display_name}' for '{channel.name}'.")


async def apply_permit_reject_settings(user_id: int, channel: discord.VoiceChannel):
    """Apply stored permit/reject entries for a user to a channel."""
    entries = await fetch_permit_reject_entries(user_id)
    for target_id, target_type, permission in entries:
        try:
            await apply_permissions_changes(channel, {"action": permission, "targets": [{"type": target_type, "id": target_id}]})
            logger.info(f"Applied {permission} for {target_id} ({target_type}) on '{channel.name}'.")
        except Exception as e:
            logger.error(f"Error applying {permission} for {target_id} on '{channel.name}': {e}")


def resolve_role_ids_for_guild(guild: discord.Guild, role_ids: Iterable[int]) -> Tuple[List[discord.Role], List[int]]:
    """Return (resolved_roles, missing_ids) for the given guild."""
    resolved: List[discord.Role] = []
    missing: List[int] = []
    for rid in role_ids:
        try:
            role = guild.get_role(int(rid)) if rid is not None else None
        except Exception:
            role = None
        if role:
            resolved.append(role)
        else:
            missing.append(rid)
    return resolved, missing


def app_command_check_configured_roles(role_ids: Iterable[int]):
    """Return an app_commands.check that ensures configured role IDs exist in the guild."""
    from discord import app_commands

    def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            raise app_commands.CheckFailure("This command can only be used in a guild.")
        resolved, _ = resolve_role_ids_for_guild(guild, role_ids)
        if not resolved:
            raise app_commands.CheckFailure("Server missing configured admin/moderator roles.")
        return True

    return app_commands.check(predicate)
"""Helpers for permission-related utilities.

Includes role-resolution helpers and small app command checks.
"""
# helpers/permissions_helper.py

import discord
from typing import Iterable
from helpers.database import Database
from helpers.logger import get_logger
from helpers.discord_api import edit_channel

logger = get_logger(__name__)

FEATURE_CONFIG = {
    "ptt": {
        "overwrite_property": "use_voice_activation",
        "db_table": "channel_ptt_settings",
        "db_column": "ptt_enabled",
        "inverted": True
    },
    "priority_speaker": {
        "overwrite_property": "priority_speaker",
        "db_table": "channel_priority_speaker_settings",
        "db_column": "priority_enabled",
        "inverted": False
    },
    "soundboard": {
        "overwrite_property": "use_soundboard",
        "db_table": "channel_soundboard_settings",
        "db_column": "soundboard_enabled",
        "inverted": False
    },
}

async def store_permit_reject_in_db(user_id: int, target_id: int, target_type: str, action: str):
    """
    Inserts or replaces a permit/reject entry in the channel_permissions table.
    action should be 'permit' or 'reject'.
    """
    async with Database.get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
            VALUES (?, ?, ?, ?)
        """, (user_id, target_id, target_type, action))
        await db.commit()
"""Permission utilities: role resolution and small app-command checks.

This module provides small, focused helpers used by cogs for voice
permission management and for validating configured admin/moderator role
IDs at runtime.
"""

from typing import Iterable, List, Tuple
import discord

from helpers.database import Database
from helpers.logger import get_logger
from helpers.discord_api import edit_channel

logger = get_logger(__name__)

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


async def store_permit_reject_in_db(user_id: int, target_id: int, target_type: str, action: str):
    """Insert or replace a permit/reject entry in the DB."""
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id, target_type, action),
        )
        await db.commit()


async def fetch_permit_reject_entries(user_id: int):
    """Return saved permit/reject entries for a user as (target_id, target_type, permission)."""
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT target_id, target_type, permission FROM channel_permissions WHERE user_id = ?",
            (user_id,),
        )
        return await cursor.fetchall()


async def apply_permissions_changes(channel: discord.VoiceChannel, perm_settings: dict):
    """Apply connect permission changes: permit/reject/lock/unlock.

    This modifies the channel overwrites mapping and calls the API helper
    to persist the change.
    """
    action = perm_settings.get("action")
    targets = perm_settings.get("targets", [])

    overwrites = channel.overwrites.copy()

    def _set_connect(target_obj, allow: bool):
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

    # Ensure recorded owner retains manage/connect
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
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
    except Exception as exc:  # pragma: no cover - best-effort logging
        logger.exception("Failed to ensure owner permissions: %s", exc)

    # Persist changes
    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info("Applied permission '%s' to channel '%s'.", action, channel.name)
    except Exception as exc:
        logger.exception("Failed to apply permission change to %s: %s", channel.name, exc)
        raise


async def reset_channel_permissions(channel: discord.VoiceChannel):
    """Reset a voice channel to sane defaults."""
    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=True, use_voice_activation=True),
        guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True),
    }
    await edit_channel(channel, overwrites=overwrites)
    logger.info("Reset permissions for channel '%s'.", channel.name)


async def update_channel_owner(channel: discord.VoiceChannel, new_owner_id: int, previous_owner_id: int):
    """Update the owner overwrite for a channel."""
    overwrites = channel.overwrites.copy()
    if prev := channel.guild.get_member(previous_owner_id):
        overwrites.pop(prev, None)
    new_owner = channel.guild.get_member(new_owner_id)
    if new_owner:
        overwrites[new_owner] = discord.PermissionOverwrite(manage_channels=True, connect=True)
    await edit_channel(channel, overwrites=overwrites)
    logger.info("Updated channel owner to '%s' for '%s'.", getattr(new_owner, "display_name", "(unknown)"), channel.name)


async def apply_permit_reject_settings(user_id: int, channel: discord.VoiceChannel):
    """Apply stored permit/reject entries for a user to the given channel."""
    entries = await fetch_permit_reject_entries(user_id)
    for target_id, target_type, permission in entries:
        try:
            await apply_permissions_changes(
                channel, {"action": permission, "targets": [{"type": target_type, "id": target_id}]}
            )
            logger.info("Applied %s for %s (%s) on %s.", permission, target_id, target_type, channel.name)
        except Exception:
            logger.exception("Failed to apply stored permission %s for %s on %s.", permission, target_id, channel.name)


def resolve_role_ids_for_guild(guild: discord.Guild, role_ids: Iterable[int]) -> Tuple[List[discord.Role], List[int]]:
    """Resolve configured role IDs to Role objects for a guild.

    Returns (resolved_roles, missing_ids). This helper is side-effect free;
    callers should log missing IDs if desired.
    """
    resolved: List[discord.Role] = []
    missing: List[int] = []
    for rid in role_ids:
        try:
            role = guild.get_role(int(rid)) if rid is not None else None
        except Exception:
            role = None
        if role:
            resolved.append(role)
        else:
            missing.append(rid)
    return resolved, missing


def app_command_check_configured_roles(role_ids: Iterable[int]):
    """Return an app_commands.check that ensures configured role IDs exist in the guild."""
    from discord import app_commands

    def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            raise app_commands.CheckFailure("This command can only be used in a guild.")
        resolved, _ = resolve_role_ids_for_guild(guild, role_ids)
        if not resolved:
            raise app_commands.CheckFailure("Server missing configured admin/moderator roles.")
        return True

    return app_commands.check(predicate)

