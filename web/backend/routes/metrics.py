"""
Metrics endpoints for the dashboard.

Provides aggregated user activity metrics: voice time, game tracking,
message counts, leaderboards, and time-series data for charting.
"""

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_bot_admin,
)
from core.pagination import is_all_guilds_mode
from core.schemas import (
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


@router.get("/overview", response_model=MetricsOverviewResponse)
async def get_metrics_overview(
    days: int = Query(default=7, ge=1, le=365),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get metrics overview: live snapshot + aggregated period data.

    Includes messages today, active voice users, top game (live), plus
    totals, averages, and leaderboard data for the given period.

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_overview(guild_id, days=days)
        return MetricsOverviewResponse(data=MetricsOverview(**result))
    except Exception:
        raise HTTPException(status_code=502, detail="Metrics unavailable")


@router.get("/voice/leaderboard", response_model=LeaderboardResponse)
async def get_voice_leaderboard(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get top users ranked by voice channel time.

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_voice_leaderboard(
            guild_id, days=days, limit=limit
        )
        return LeaderboardResponse(entries=result.get("entries", []))
    except Exception:
        raise HTTPException(
            status_code=502, detail="Voice leaderboard unavailable"
        )


@router.get("/messages/leaderboard", response_model=LeaderboardResponse)
async def get_message_leaderboard(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get top users ranked by message count.

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_message_leaderboard(
            guild_id, days=days, limit=limit
        )
        return LeaderboardResponse(entries=result.get("entries", []))
    except Exception:
        raise HTTPException(
            status_code=502, detail="Message leaderboard unavailable"
        )


@router.get("/games/top", response_model=TopGamesResponse)
async def get_top_games(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get top games ranked by total play time.

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_top_games(
            guild_id, days=days, limit=limit
        )
        return TopGamesResponse(games=result.get("games", []))
    except Exception:
        raise HTTPException(
            status_code=502, detail="Game stats unavailable"
        )


@router.get("/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(
    metric: str = Query(default="messages", pattern="^(messages|voice|games)$"),
    days: int = Query(default=7, ge=1, le=365),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get hourly time-series data for charts.

    Supports metrics: messages, voice, games

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_timeseries(
            guild_id, metric=metric, days=days
        )
        return TimeSeriesResponse(
            metric=result.get("metric", metric),
            days=result.get("days", days),
            data=result.get("data", []),
        )
    except Exception:
        raise HTTPException(
            status_code=502, detail="Timeseries unavailable"
        )


@router.get("/user/{user_id}", response_model=UserMetricsResponse)
async def get_user_metrics(
    user_id: int,
    days: int = Query(default=7, ge=1, le=365),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get detailed metrics for a specific user.

    Includes totals, daily averages, game breakdown, and time-series.

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_user(guild_id, user_id, days=days)
        return UserMetricsResponse(data=UserMetrics(**result))
    except Exception:
        raise HTTPException(
            status_code=502, detail="User metrics unavailable"
        )


@router.delete("/user/{user_id}")
async def delete_user_metrics(
    user_id: int,
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Delete all metrics data for a specific user (data erasure).

    Supports GDPR right-to-erasure and Discord data deletion requests.

    Requires: Bot Admin role or higher
    """
    guild_id = _resolve_guild_id(current_user)

    try:
        result = await internal_api.delete_metrics_user(guild_id, user_id)
        return result
    except Exception:
        raise HTTPException(
            status_code=502, detail="Failed to delete user metrics"
        )
