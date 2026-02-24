"""
New-member role lifecycle service.

Assigns a configurable "new member" role on first successful verification,
removes it after a configured number of days or on manual removal by staff.
The module is toggled per-guild via guild settings.

Guild settings keys (stored in guild_settings table):
    new_member_role.enabled            – bool  (default False)
    new_member_role.role_id            – str   (Discord role snowflake)
    new_member_role.duration_days      – int   (how long to keep the role)
    new_member_role.max_server_age_days – int|None (skip if member joined > N days ago; null = no gate)

AI Notes:
    * The ``new_member_roles`` table (see services/db/schema.py) is keyed on
      (guild_id, user_id) so each user can only have one active assignment per guild.
    * ``assign_if_eligible`` is idempotent — calling it multiple times for the
      same user+guild will not create duplicate records.
    * ``process_expired_roles`` is designed to run periodically from a background
      loop (see ``cogs/admin/new_member_role_worker.py``).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from services.config_service import (
    CONFIG_NEW_MEMBER_DURATION_DAYS,
    CONFIG_NEW_MEMBER_ENABLED,
    CONFIG_NEW_MEMBER_MAX_SERVER_AGE_DAYS,
    CONFIG_NEW_MEMBER_ROLE_ID,
    ConfigService,
)
from services.db.repository import BaseRepository
from utils.logging import get_logger

if TYPE_CHECKING:
    import discord

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


async def get_new_member_config(
    config: ConfigService,
    guild_id: int,
) -> dict[str, Any]:
    """Return parsed new-member-role settings for *guild_id*.

    Returns:
        dict with keys ``enabled``, ``role_id``, ``duration_days``,
        ``max_server_age_days``.
    """
    enabled = await config.get(guild_id, CONFIG_NEW_MEMBER_ENABLED, False)
    role_id_raw = await config.get(guild_id, CONFIG_NEW_MEMBER_ROLE_ID, None)
    duration_days = await config.get(
        guild_id, CONFIG_NEW_MEMBER_DURATION_DAYS, 14, parser=int
    )
    max_server_age_raw = await config.get(
        guild_id, CONFIG_NEW_MEMBER_MAX_SERVER_AGE_DAYS, None
    )
    max_server_age_days: int | None = None
    if max_server_age_raw is not None:
        try:
            max_server_age_days = int(max_server_age_raw)
        except (ValueError, TypeError):
            max_server_age_days = None

    # Coerce enabled to bool (could be stored as string/int in JSON)
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("true", "1", "yes")
    else:
        enabled = bool(enabled)

    role_id: str | None = None
    if role_id_raw is not None:
        try:
            role_id = str(int(role_id_raw))
        except (ValueError, TypeError):
            role_id = None

    return {
        "enabled": enabled,
        "role_id": role_id,
        "duration_days": duration_days if isinstance(duration_days, int) and duration_days > 0 else 14,
        "max_server_age_days": max_server_age_days,
    }


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def _member_server_age_days(member: discord.Member) -> int | None:
    """Return days since the member joined the guild, or None if unknown."""
    joined_at = getattr(member, "joined_at", None)
    if joined_at is None:
        return None
    now = datetime.now(timezone.utc)
    delta = now - joined_at
    return delta.days


def is_eligible(
    member: discord.Member,
    *,
    max_server_age_days: int | None,
) -> bool:
    """Check whether *member* passes the server-age gate.

    Rules:
        * If ``max_server_age_days`` is ``None`` → always eligible.
        * If ``joined_at`` is unavailable → eligible (fail-open per plan).
        * Otherwise eligible when member's server age < max_server_age_days.
    """
    if max_server_age_days is None:
        return True
    age = _member_server_age_days(member)
    if age is None:
        return True  # fail-open
    return age < max_server_age_days


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def _has_previous_assignment(guild_id: int, user_id: int) -> bool:
    """Return True if a record (active or not) exists for this user+guild."""
    row = await BaseRepository.fetch_one(
        "SELECT 1 FROM new_member_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    return row is not None


async def _insert_assignment(
    guild_id: int,
    user_id: int,
    role_id: int,
    assigned_at: int,
    expires_at: int,
) -> None:
    """Insert a new active assignment row."""
    await BaseRepository.execute(
        """
        INSERT OR IGNORE INTO new_member_roles
            (guild_id, user_id, role_id, assigned_at, expires_at, active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (guild_id, user_id, role_id, assigned_at, expires_at),
    )


async def mark_removed(
    guild_id: int,
    user_id: int,
    reason: str = "manual",
) -> None:
    """Mark an active assignment as removed."""
    now = int(time.time())
    await BaseRepository.execute(
        """
        UPDATE new_member_roles
        SET active = 0, removed_at = ?, removed_reason = ?
        WHERE guild_id = ? AND user_id = ? AND active = 1
        """,
        (now, reason, guild_id, user_id),
    )


async def get_expired_assignments(
    batch_size: int = 50,
) -> list[tuple[int, int, int]]:
    """Return up to *batch_size* ``(guild_id, user_id, role_id)`` tuples whose
    ``expires_at`` has passed and are still active."""
    now = int(time.time())
    rows = await BaseRepository.fetch_all(
        """
        SELECT guild_id, user_id, role_id
        FROM new_member_roles
        WHERE active = 1 AND expires_at <= ?
        ORDER BY expires_at ASC
        LIMIT ?
        """,
        (now, batch_size),
    )
    return [(int(r[0]), int(r[1]), int(r[2])) for r in rows]


async def get_active_assignment(
    guild_id: int,
    user_id: int,
) -> tuple[int, int, int, int] | None:
    """Return ``(role_id, assigned_at, expires_at, active)`` or None."""
    row = await BaseRepository.fetch_one(
        """
        SELECT role_id, assigned_at, expires_at, active
        FROM new_member_roles
        WHERE guild_id = ? AND user_id = ? AND active = 1
        """,
        (guild_id, user_id),
    )
    if row is None:
        return None
    return (int(row[0]), int(row[1]), int(row[2]), int(row[3]))


# ---------------------------------------------------------------------------
# Core actions
# ---------------------------------------------------------------------------


async def assign_if_eligible(
    member: discord.Member,
    bot: Any,
) -> bool:
    """Assign the new-member role to *member* if eligible and not previously assigned.

    Returns True if the role was newly assigned, False otherwise.
    """
    if not hasattr(bot, "services") or bot.services is None:
        return False

    cfg = await get_new_member_config(bot.services.config, member.guild.id)
    if not cfg["enabled"] or not cfg["role_id"]:
        return False

    # First-verification-only: skip if user already has a record
    if await _has_previous_assignment(member.guild.id, member.id):
        logger.debug(
            "New-member role already assigned previously for user %s in guild %s",
            member.id,
            member.guild.id,
        )
        return False

    # Server-age gate
    if not is_eligible(member, max_server_age_days=cfg["max_server_age_days"]):
        logger.debug(
            "User %s not eligible for new-member role in guild %s (server age gate)",
            member.id,
            member.guild.id,
        )
        return False

    # Resolve the Discord role object
    role_id_int = int(cfg["role_id"])
    role = member.guild.get_role(role_id_int)
    if role is None:
        logger.warning(
            "New-member role %s not found in guild %s",
            cfg["role_id"],
            member.guild.id,
        )
        return False

    # Assign the role via Discord API
    try:
        await member.add_roles(role, reason="New member role (first verification)")
    except Exception:
        logger.exception(
            "Failed to assign new-member role to user %s in guild %s",
            member.id,
            member.guild.id,
        )
        return False

    # Persist
    now = int(time.time())
    expires_at = now + cfg["duration_days"] * 86400
    await _insert_assignment(
        member.guild.id, member.id, role_id_int, now, expires_at
    )
    logger.info(
        "Assigned new-member role %s to user %s in guild %s (expires in %d days)",
        cfg["role_id"],
        member.id,
        member.guild.id,
        cfg["duration_days"],
    )
    return True


async def remove_expired_role(
    guild_id: int,
    user_id: int,
    role_id: int,
    bot: Any,
) -> bool:
    """Remove an expired new-member role from a user. Returns True on success."""
    guild = bot.get_guild(guild_id)
    if guild is None:
        logger.warning("Guild %s not found when removing expired new-member role", guild_id)
        await mark_removed(guild_id, user_id, reason="expired")
        return False

    member = guild.get_member(user_id)
    if member is None:
        logger.debug("Member %s not found in guild %s for expired role removal", user_id, guild_id)
        await mark_removed(guild_id, user_id, reason="expired")
        return False

    role = guild.get_role(role_id)
    if role is None:
        logger.warning("New-member role %s no longer exists in guild %s", role_id, guild_id)
        await mark_removed(guild_id, user_id, reason="expired")
        return False

    try:
        await member.remove_roles(role, reason="New member role expired")
    except Exception:
        logger.exception(
            "Failed to remove expired new-member role %s from user %s in guild %s",
            role_id,
            user_id,
            guild_id,
        )
        return False

    await mark_removed(guild_id, user_id, reason="expired")
    logger.info(
        "Removed expired new-member role %s from user %s in guild %s",
        role_id,
        user_id,
        guild_id,
    )
    return True


async def process_expired_roles(bot: Any, batch_size: int = 50) -> int:
    """Process a batch of expired assignments. Returns number processed."""
    expired = await get_expired_assignments(batch_size)
    count = 0
    for guild_id, user_id, role_id in expired:
        await remove_expired_role(guild_id, user_id, role_id, bot)
        count += 1
    return count
