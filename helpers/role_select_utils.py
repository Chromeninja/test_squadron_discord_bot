"""Shared helpers for role selection views."""

from __future__ import annotations

from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_role_ids(raw_roles: Any, guild_id: int | None, key: str) -> list[int]:
    """Coerce role identifiers into unique ints, ignoring invalid entries."""

    def _walk(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):  # cover typical iterables
            flattened: list[Any] = []
            for item in value:
                flattened.extend(_walk(item))
            return flattened
        return [value]

    normalized: list[int] = []
    seen: set[int] = set()

    for raw in _walk(raw_roles):
        try:
            role_id = int(raw)
        except (TypeError, ValueError):
            logger.warning("Invalid role id '%s' for %s in guild %s", raw, key, guild_id)
            continue
        if role_id < 0 or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)

    return normalized


async def load_selectable_roles(bot, guild, key: str = "roles.selectable") -> list[int]:
    """Fetch selectable roles for a guild via ConfigService, normalized to ints."""
    if guild is None or not getattr(bot, "services", None):
        return []

    config_service = getattr(bot.services, "config", None)
    if not config_service:
        return []

    try:
        roles = await config_service.get_guild_setting(guild.id, key, [])
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to load %s for guild %s: %s", key, guild.id, exc)
        return []

    normalized = _normalize_role_ids(roles, guild.id, key)
    if not normalized:
        logger.warning("No %s configured for guild %s", key, guild.id)
    return normalized


def refresh_role_select(select_obj, guild, allowed_roles: list[int]) -> None:
    """Update allowed roles and refresh options on a select component."""
    select_obj.allowed_roles = allowed_roles or []
    if guild:
        select_obj.refresh_options(guild)
