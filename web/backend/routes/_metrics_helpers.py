"""Helper utilities for metrics route payload shaping and activity filters."""

from __future__ import annotations

import contextlib
import logging

from core.dependencies import InternalAPIClient
from core.schemas import MessageLeaderboardEntry, VoiceLeaderboardEntry
from core.pagination import is_all_guilds_mode
from core.schemas import UserProfile
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def resolve_guild_id(current_user: UserProfile) -> int:
    """Extract and validate the active guild ID from the current session."""
    if not current_user.active_guild_id or is_all_guilds_mode(
        current_user.active_guild_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Metrics require a specific guild selection. "
                "Cross-guild mode is not supported."
            ),
        )
    return int(current_user.active_guild_id)


async def resolve_activity_filter(
    internal_api: InternalAPIClient,
    guild_id: int,
    dimension: str | None,
    tier: str | None,
    days: int = 30,
) -> list[int] | None:
    """Resolve dimension+tier to user IDs, or ``None`` when no filter is set."""
    if not dimension or not tier:
        return None

    raw_dims = [part.strip() for part in dimension.split(",") if part.strip()]
    if not raw_dims:
        return None

    resolved_dims: list[str] = []
    for raw in raw_dims:
        resolved = "combined" if raw == "all" else raw
        if resolved not in resolved_dims:
            resolved_dims.append(resolved)

    raw_tiers = [part.strip() for part in tier.split(",") if part.strip()]
    if not raw_tiers:
        return None

    resolved_tiers: list[str] = []
    for raw in raw_tiers:
        if raw not in resolved_tiers:
            resolved_tiers.append(raw)

    try:
        bulk = await internal_api.get_activity_group_members_bulk(
            guild_id,
            resolved_dims,
            resolved_tiers,
            days=days,
        )
        merged_user_ids: set[int] = set()
        for _dim_key, tier_map in bulk.items():
            if not isinstance(tier_map, dict):
                continue
            for _tier_key, uid_list in tier_map.items():
                if not isinstance(uid_list, list):
                    continue
                for uid in uid_list:
                    try:
                        merged_user_ids.add(int(uid))
                    except (TypeError, ValueError):
                        continue
        return sorted(merged_user_ids)
    except Exception as exc:
        logger.warning("Failed to resolve activity filter", exc_info=exc)
        return []


def coerce_metric_value(raw_value: object) -> int | None:
    """Coerce loosely-typed metric values to integers when possible."""
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        with contextlib.suppress(ValueError):
            return int(float(raw_value))
    return None


def normalize_leaderboard_entries(
    entries: list[object],
    *,
    metric_field: str,
) -> list[dict[str, object]]:
    """Normalize leaderboard entries for stable frontend payloads."""
    normalized_entries: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized = dict(entry)
        if "user_id" in normalized:
            normalized["user_id"] = str(normalized["user_id"])
        if metric_field not in normalized and "value" in normalized:
            coerced_value = coerce_metric_value(normalized.get("value"))
            if coerced_value is not None:
                normalized[metric_field] = coerced_value
        normalized.pop("value", None)
        normalized_entries.append(normalized)
    return normalized_entries


def normalize_timeseries_data(data: list[object]) -> list[dict[str, object]]:
    """Filter timeseries payloads down to dict items only."""
    return [dict(item) for item in data if isinstance(item, dict)]


def build_voice_leaderboard_entries(
    entries: list[object],
) -> list[VoiceLeaderboardEntry]:
    """Build typed voice leaderboard entries for dashboard response."""
    typed_entries: list[VoiceLeaderboardEntry] = []
    for entry in normalize_leaderboard_entries(entries, metric_field="total_seconds"):
        total_seconds = coerce_metric_value(entry.get("total_seconds"))
        if total_seconds is None:
            continue
        username = entry.get("username")
        avatar_url = entry.get("avatar_url")
        typed_entries.append(
            VoiceLeaderboardEntry(
                user_id=str(entry.get("user_id", "")),
                total_seconds=total_seconds,
                username=username if isinstance(username, str) else None,
                avatar_url=avatar_url if isinstance(avatar_url, str) else None,
            )
        )
    return typed_entries


def build_message_leaderboard_entries(
    entries: list[object],
) -> list[MessageLeaderboardEntry]:
    """Build typed message leaderboard entries for dashboard response."""
    typed_entries: list[MessageLeaderboardEntry] = []
    for entry in normalize_leaderboard_entries(entries, metric_field="total_messages"):
        total_messages = coerce_metric_value(entry.get("total_messages"))
        if total_messages is None:
            continue
        username = entry.get("username")
        avatar_url = entry.get("avatar_url")
        typed_entries.append(
            MessageLeaderboardEntry(
                user_id=str(entry.get("user_id", "")),
                total_messages=total_messages,
                username=username if isinstance(username, str) else None,
                avatar_url=avatar_url if isinstance(avatar_url, str) else None,
            )
        )
    return typed_entries
