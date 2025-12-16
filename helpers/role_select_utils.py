"""Shared helpers for role selection views."""

from __future__ import annotations

from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


_NOT_SET = object()


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
            logger.warning(
                "Invalid role id '%s' for %s in guild %s", raw, key, guild_id
            )
            continue
        if role_id < 0 or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)

    return normalized


async def load_selectable_roles(
    bot, guild, key: str | None = None
) -> list[int]:
    """Fetch selectable roles for a guild via ConfigService, normalized to ints.

    Prefers the current DB key ("selectable_roles") and falls back to the
    legacy key ("roles.selectable") for backward compatibility.
    """
    if guild is None or not getattr(bot, "services", None):
        return []

    config_service = getattr(bot.services, "config", None)
    if not config_service:
        return []

    keys_to_try = [key] if key else ["selectable_roles", "roles.selectable"]

    for current_key in keys_to_try:
        try:
            roles = await config_service.get_guild_setting(
                guild.id, current_key, _NOT_SET
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to load %s for guild %s: %s", current_key, guild.id, exc
            )
            continue

        if roles is _NOT_SET:
            # Nothing stored for this key; try the next candidate
            continue

        normalized = _normalize_role_ids(roles, guild.id, current_key)
        if not normalized:
            logger.warning("No %s configured for guild %s", current_key, guild.id)
        return normalized

    # No configured values found in any key
    return []


def refresh_role_select(select_obj, guild, allowed_roles: list[int]) -> None:
    """Update allowed roles and refresh options on a select component."""
    select_obj.allowed_roles = allowed_roles or []
    if guild:
        select_obj.refresh_options(guild)
