"""
Metrics endpoints for the dashboard.

Provides aggregated user activity metrics: voice time, game tracking,
message counts, leaderboards, and time-series data for charting.
"""

import logging

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_discord_manager,
)
from core.pagination import is_all_guilds_mode
from core.schemas import (
    ActivityGroupCounts,
    ActivityGroupCountsResponse,
    LeaderboardResponse,
    MetricsOverview,
    MetricsOverviewResponse,
    TimeSeriesResponse,
    TopGamesResponse,
    UserMetrics,
    UserMetricsResponse,
    UserProfile,
)
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)


def _resolve_guild_id(current_user: UserProfile) -> int:
    """
    Extract and validate the active guild ID from the current user session.

    Raises HTTPException if no guild is selected or in cross-guild mode
    (metrics are per-guild only).
    """
    if not current_user.active_guild_id or is_all_guilds_mode(
        current_user.active_guild_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Metrics require a specific guild selection. Cross-guild mode is not supported.",
        )
    return int(current_user.active_guild_id)


async def _resolve_activity_filter(
    internal_api: InternalAPIClient,
    guild_id: int,
    dimension: str | None,
    tier: str | None,
    days: int = 30,
) -> list[int] | None:
    """Resolve dimension+tier into a list of user IDs, or None if no filter.

    Supports comma-separated dimensions and tiers; users are matched if they
    belong to the selected tier in ANY selected dimension.

    Uses the bulk internal endpoint to resolve all dimension×tier combos in a
    single HTTP call instead of issuing one request per pair.
    """
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
        return sorted(merged_user_ids) if merged_user_ids else None
    except Exception:
        logger.warning(
            "Failed to resolve activity filter dimension=%s tier=%s", dimension, tier
        )
        return None


@router.get("/overview", response_model=MetricsOverviewResponse)
async def get_metrics_overview(
    days: int = Query(default=7, ge=1, le=365),
    dimension: str | None = Query(
        default=None,
        pattern="^(all|voice|chat|game|combined)(,(all|voice|chat|game|combined))*$",
    ),
    tier: str | None = Query(
        default=None,
        pattern="^(hardcore|regular|casual|reserve|inactive)(,(hardcore|regular|casual|reserve|inactive))*$",
    ),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get metrics overview: live snapshot + aggregated period data.

    Optional dimension/tier filter to scope to an activity group.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_overview(
            guild_id, days=days, user_ids=user_ids
        )
        return MetricsOverviewResponse(data=MetricsOverview(**result))
    except Exception:
        raise HTTPException(status_code=502, detail="Metrics unavailable")


@router.get("/voice/leaderboard", response_model=LeaderboardResponse)
async def get_voice_leaderboard(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    dimension: str | None = Query(
        default=None,
        pattern="^(all|voice|chat|game|combined)(,(all|voice|chat|game|combined))*$",
    ),
    tier: str | None = Query(
        default=None,
        pattern="^(hardcore|regular|casual|reserve|inactive)(,(hardcore|regular|casual|reserve|inactive))*$",
    ),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get top users ranked by voice channel time.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_voice_leaderboard(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        entries = result.get("entries", [])
        normalized_entries: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            normalized = dict(entry)
            if "user_id" in normalized:
                normalized["user_id"] = str(normalized["user_id"])
            normalized_entries.append(normalized)
        return LeaderboardResponse(entries=normalized_entries)
    except Exception:
        raise HTTPException(status_code=502, detail="Voice leaderboard unavailable")


@router.get("/messages/leaderboard", response_model=LeaderboardResponse)
async def get_message_leaderboard(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    dimension: str | None = Query(
        default=None,
        pattern="^(all|voice|chat|game|combined)(,(all|voice|chat|game|combined))*$",
    ),
    tier: str | None = Query(
        default=None,
        pattern="^(hardcore|regular|casual|reserve|inactive)(,(hardcore|regular|casual|reserve|inactive))*$",
    ),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get top users ranked by message count.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_message_leaderboard(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        entries = result.get("entries", [])
        normalized_entries: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            normalized = dict(entry)
            if "user_id" in normalized:
                normalized["user_id"] = str(normalized["user_id"])
            normalized_entries.append(normalized)
        return LeaderboardResponse(entries=normalized_entries)
    except Exception:
        raise HTTPException(status_code=502, detail="Message leaderboard unavailable")


@router.get("/games/top", response_model=TopGamesResponse)
async def get_top_games(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    dimension: str | None = Query(
        default=None,
        pattern="^(all|voice|chat|game|combined)(,(all|voice|chat|game|combined))*$",
    ),
    tier: str | None = Query(
        default=None,
        pattern="^(hardcore|regular|casual|reserve|inactive)(,(hardcore|regular|casual|reserve|inactive))*$",
    ),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get top games ranked by total play time.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_top_games(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        return TopGamesResponse(games=result.get("games", []))
    except Exception:
        raise HTTPException(status_code=502, detail="Game stats unavailable")


@router.get("/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(
    metric: str = Query(default="messages", pattern="^(messages|voice|games)$"),
    days: int = Query(default=7, ge=1, le=365),
    dimension: str | None = Query(
        default=None,
        pattern="^(all|voice|chat|game|combined)(,(all|voice|chat|game|combined))*$",
    ),
    tier: str | None = Query(
        default=None,
        pattern="^(hardcore|regular|casual|reserve|inactive)(,(hardcore|regular|casual|reserve|inactive))*$",
    ),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get hourly time-series data for charts.

    Supports metrics: messages, voice, games

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_timeseries(
            guild_id, metric=metric, days=days, user_ids=user_ids
        )
        return TimeSeriesResponse(
            metric=result.get("metric", metric),
            days=result.get("days", days),
            data=result.get("data", []),
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Timeseries unavailable")


@router.get("/activity-groups", response_model=ActivityGroupCountsResponse)
async def get_activity_groups(
    days: int = Query(default=7, ge=1, le=365),
    dimension: str | None = Query(
        default=None,
        pattern="^(all|voice|chat|game|combined)(,(all|voice|chat|game|combined))*$",
    ),
    tier: str | None = Query(
        default=None,
        pattern="^(hardcore|regular|casual|reserve|inactive)(,(hardcore|regular|casual|reserve|inactive))*$",
    ),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get activity group tier counts per dimension (voice, chat, game, combined).

    Returns count of members in each tier (hardcore, regular, casual, reserve, inactive)
    for each activity dimension.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_activity_groups(
            guild_id, days=days, user_ids=user_ids
        )
        return ActivityGroupCountsResponse(data=ActivityGroupCounts(**result))
    except Exception:
        raise HTTPException(status_code=502, detail="Activity groups unavailable")


@router.get("/user/{user_id}", response_model=UserMetricsResponse)
async def get_user_metrics(
    user_id: int,
    days: int = Query(default=7, ge=1, le=365),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get detailed metrics for a specific user.

    Includes totals, daily averages, game breakdown, time-series,
    and per-dimension activity tiers.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_user(guild_id, user_id, days=days)

        raw_user_id = result.get("user_id")
        result["user_id"] = str(raw_user_id if raw_user_id is not None else user_id)

        for tier_key in ("voice_tier", "chat_tier", "game_tier", "combined_tier"):
            result[tier_key] = result.get(tier_key) or "inactive"

        return UserMetricsResponse(data=UserMetrics(**result))
    except Exception as exc:
        logger.exception(
            "User metrics fetch failed for user_id=%s guild_id=%s", user_id, guild_id
        )
        raise HTTPException(status_code=502, detail="User metrics unavailable") from exc


@router.delete("/user/{user_id}")
async def delete_user_metrics(
    user_id: int,
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Delete all metrics data for a specific user (data erasure).

    Supports GDPR right-to-erasure and Discord data deletion requests.

    Requires: Discord Manager role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.delete_metrics_user(guild_id, user_id)
        return result
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to delete user metrics")
