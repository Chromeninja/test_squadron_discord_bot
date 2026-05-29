from __future__ import annotations

"""Shared role and role-switch helper functions."""

from typing import TYPE_CHECKING, Any

from .schemas import GuildPermission, UserProfile

if TYPE_CHECKING:
    from collections.abc import Mapping

ROLE_HIERARCHY: dict[str, int] = {
    "bot_owner": 7,
    "bot_admin": 6,
    "discord_manager": 5,
    "moderator": 4,
    "event_coordinator": 3,
    "staff": 2,
    "user": 1,
}


def _has_minimum_role(user_role: str, required_role: str) -> bool:
    """Return True when user_role satisfies the required_role threshold."""
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def _coerce_role_level(value: object) -> str | None:
    """Return a valid role level string when present."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in ROLE_HIERARCHY:
        return normalized
    return None


def get_base_role_level(permission: GuildPermission | Mapping[str, Any] | None) -> str:
    """Return the real role for a guild permission entry."""
    if permission is None:
        return "user"

    if isinstance(permission, GuildPermission):
        return (
            _coerce_role_level(permission.base_role_level)
            or _coerce_role_level(permission.role_level)
            or "user"
        )

    return (
        _coerce_role_level(permission.get("base_role_level"))
        or _coerce_role_level(permission.get("role_level"))
        or "user"
    )


def get_assumed_role_level(
    permission: GuildPermission | Mapping[str, Any] | None,
) -> str | None:
    """Return the assumed role for a guild permission entry when present."""
    if permission is None:
        return None

    if isinstance(permission, GuildPermission):
        return _coerce_role_level(permission.assumed_role_level)

    return _coerce_role_level(permission.get("assumed_role_level"))


def can_assume_role(base_role_level: str, target_role_level: str) -> bool:
    """Return True when target_role_level is a valid downgrade from base_role_level."""
    base_level = ROLE_HIERARCHY.get(base_role_level, 0)
    target_level = ROLE_HIERARCHY.get(target_role_level, 0)
    if base_role_level not in ROLE_HIERARCHY or target_role_level not in ROLE_HIERARCHY:
        return False
    if target_role_level == "bot_owner":
        return False
    return target_level < base_level


def resolve_role_level(
    base_role_level: str,
    assumed_role_level: str | None,
) -> str:
    """Resolve role_level after applying a valid assumed-role downgrade."""
    if assumed_role_level and can_assume_role(base_role_level, assumed_role_level):
        return assumed_role_level
    return base_role_level


def normalize_guild_permission(
    guild_id: str,
    permission: GuildPermission | Mapping[str, Any],
) -> GuildPermission:
    """Normalize a guild permission payload to include base/assumed role fields."""
    data = (
        permission.model_dump()
        if isinstance(permission, GuildPermission)
        else dict(permission)
    )
    base_role_level = get_base_role_level(data)
    assumed_role_level = get_assumed_role_level(data)
    role_level = resolve_role_level(base_role_level, assumed_role_level)

    return GuildPermission(
        guild_id=str(data.get("guild_id") or guild_id),
        role_level=role_level,
        base_role_level=base_role_level,
        assumed_role_level=(
            assumed_role_level if role_level != base_role_level else None
        ),
        source=str(data.get("source") or ""),
    )


def normalize_authorized_guilds(
    authorized_guilds: Mapping[str, GuildPermission | Mapping[str, Any]] | None,
) -> dict[str, GuildPermission]:
    """Normalize all guild permissions from a session payload or profile model."""
    if not authorized_guilds:
        return {}

    normalized: dict[str, GuildPermission] = {}
    for guild_id, permission in authorized_guilds.items():
        normalized[guild_id] = normalize_guild_permission(guild_id, permission)
    return normalized


def normalize_session_user_data(user_data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a session payload with normalized guild permission entries."""
    normalized = dict(user_data)
    authorized_guilds = normalize_authorized_guilds(
        normalized.get("authorized_guilds") or {}
    )
    normalized["authorized_guilds"] = {
        guild_id: permission.model_dump()
        for guild_id, permission in authorized_guilds.items()
    }
    return normalized


def update_guild_base_role(
    permission: GuildPermission | Mapping[str, Any],
    guild_id: str,
    base_role_level: str,
) -> GuildPermission:
    """Update the real role for a guild permission and preserve valid assumptions."""
    data = (
        permission.model_dump()
        if isinstance(permission, GuildPermission)
        else dict(permission)
    )
    data["base_role_level"] = base_role_level
    return normalize_guild_permission(guild_id, data)


def set_guild_assumed_role(
    permission: GuildPermission | Mapping[str, Any],
    guild_id: str,
    assumed_role_level: str,
) -> GuildPermission:
    """Apply a validated assumed role to a guild permission entry."""
    data = (
        permission.model_dump()
        if isinstance(permission, GuildPermission)
        else dict(permission)
    )
    base_role_level = get_base_role_level(data)
    if not can_assume_role(base_role_level, assumed_role_level):
        raise ValueError("Target role is not a valid downgrade")
    data["assumed_role_level"] = assumed_role_level
    return normalize_guild_permission(guild_id, data)


def clear_guild_assumed_role(
    permission: GuildPermission | Mapping[str, Any],
    guild_id: str,
) -> GuildPermission:
    """Remove an assumed role from a guild permission entry."""
    data = (
        permission.model_dump()
        if isinstance(permission, GuildPermission)
        else dict(permission)
    )
    data["assumed_role_level"] = None
    return normalize_guild_permission(guild_id, data)


def get_active_guild_permission(user: UserProfile) -> GuildPermission | None:
    """Return the current active guild permission for a user."""
    if not user.active_guild_id:
        return None
    return user.authorized_guilds.get(user.active_guild_id)
