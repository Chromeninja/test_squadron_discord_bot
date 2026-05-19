"""Metrics endpoints for dashboard activity and leaderboard data."""

import asyncio
import contextlib
import logging
import time

from ._metrics_helpers import (
    build_message_leaderboard_entries,
    build_voice_leaderboard_entries,
    normalize_leaderboard_entries,
    normalize_timeseries_data,
    resolve_guild_id,
    resolve_activity_filter,
)
from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_discord_manager,
)
from core.schemas import (
    ActivityGroupCounts,
    ActivityGroupCountsResponse,
    DashboardMetricsBundle,
    DashboardMetricsResponse,
    GameMetrics,
    GameMetricsResponse,
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

from helpers.audit import log_admin_action

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_GAME_DETAIL_FILTER_USERS = 1000

# Backward-compatible alias for tests and existing monkeypatch hooks.
_resolve_activity_filter = resolve_activity_filter


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
    guild_id = resolve_guild_id(current_user)
    started_at = time.perf_counter()

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_overview(
            guild_id, days=days, user_ids=user_ids
        )
        return MetricsOverviewResponse(data=MetricsOverview(**result))
    except Exception as exc:
        logger.exception("metrics.overview unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Metrics unavailable") from exc
    finally:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("metrics.overview completed elapsed_ms=%s", elapsed_ms)


@router.get("/dashboard", response_model=DashboardMetricsResponse)
async def get_dashboard_metrics(
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
) -> DashboardMetricsResponse:
    """Get a bundled metrics payload optimized for the dashboard page."""
    guild_id = resolve_guild_id(current_user)
    started_at = time.perf_counter()

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        (
            overview_result,
            voice_result,
            message_result,
            top_games_result,
            message_timeseries_result,
            voice_timeseries_result,
            activity_groups_result,
        ) = await asyncio.gather(
            internal_api.get_metrics_overview(guild_id, days=days, user_ids=user_ids),
            internal_api.get_metrics_voice_leaderboard(
                guild_id, days=days, limit=10, user_ids=user_ids
            ),
            internal_api.get_metrics_message_leaderboard(
                guild_id, days=days, limit=10, user_ids=user_ids
            ),
            internal_api.get_metrics_top_games(
                guild_id, days=days, limit=10, user_ids=user_ids
            ),
            internal_api.get_metrics_timeseries(
                guild_id, metric="messages", days=days, user_ids=user_ids
            ),
            internal_api.get_metrics_timeseries(
                guild_id, metric="voice", days=days, user_ids=user_ids
            ),
            internal_api.get_activity_groups(guild_id, days=days, user_ids=user_ids),
        )

        return DashboardMetricsResponse(
            data=DashboardMetricsBundle(
                overview=MetricsOverview(**overview_result),
                voice_leaderboard=build_voice_leaderboard_entries(
                    voice_result.get("entries", [])
                ),
                message_leaderboard=build_message_leaderboard_entries(
                    message_result.get("entries", [])
                ),
                top_games=top_games_result.get("games", []),
                message_timeseries=normalize_timeseries_data(
                    message_timeseries_result.get("data", [])
                ),
                voice_timeseries=normalize_timeseries_data(
                    voice_timeseries_result.get("data", [])
                ),
                activity_counts=ActivityGroupCounts(**activity_groups_result),
            )
        )
    except Exception as exc:
        logger.exception("Bundled dashboard metrics unavailable", exc_info=exc)
        raise HTTPException(
            status_code=502, detail="Bundled dashboard metrics unavailable"
        ) from exc
    finally:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("metrics.dashboard completed elapsed_ms=%s", elapsed_ms)


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
    guild_id = resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_voice_leaderboard(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        normalized_entries = normalize_leaderboard_entries(
            result.get("entries", []), metric_field="total_seconds"
        )
        return LeaderboardResponse(entries=normalized_entries)
    except Exception as exc:
        logger.exception("metrics.voice_leaderboard unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Voice leaderboard unavailable") from exc


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
    guild_id = resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_message_leaderboard(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        normalized_entries = normalize_leaderboard_entries(
            result.get("entries", []), metric_field="total_messages"
        )
        return LeaderboardResponse(entries=normalized_entries)
    except Exception as exc:
        logger.exception("metrics.message_leaderboard unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Message leaderboard unavailable") from exc


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
    guild_id = resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_top_games(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        return TopGamesResponse(games=result.get("games", []))
    except Exception as exc:
        logger.exception("metrics.top_games unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Game stats unavailable") from exc


@router.get("/games/detail", response_model=GameMetricsResponse)
async def get_game_metrics(
    game_name: str = Query(min_length=1, max_length=100),
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=5, ge=1, le=20),
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
    Get detailed metrics for a specific game, including top players.

    Requires: Discord Manager role or higher
    """
    guild_id = resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        if user_ids is not None and len(user_ids) > MAX_GAME_DETAIL_FILTER_USERS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Selected activity filter matches too many users for game detail. "
                    "Please narrow your filters."
                ),
            )
        result = await internal_api.get_metrics_game(
            guild_id,
            game_name=game_name,
            days=days,
            limit=limit,
            user_ids=user_ids,
        )

        top_players = result.get("top_players", [])
        normalized_players: list[dict] = []
        for entry in top_players:
            if not isinstance(entry, dict):
                continue
            normalized = dict(entry)
            if "user_id" in normalized:
                normalized["user_id"] = str(normalized["user_id"])
            normalized_players.append(normalized)
        result["top_players"] = normalized_players

        return GameMetricsResponse(data=GameMetrics(**result))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("metrics.game_detail unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Game metrics unavailable") from exc


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
    guild_id = resolve_guild_id(current_user)
    started_at = time.perf_counter()

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
    except Exception as exc:
        logger.exception("metrics.timeseries unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Timeseries unavailable") from exc
    finally:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("metrics.timeseries completed elapsed_ms=%s", elapsed_ms)


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
    guild_id = resolve_guild_id(current_user)
    started_at = time.perf_counter()

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_activity_groups(
            guild_id, days=days, user_ids=user_ids
        )
        return ActivityGroupCountsResponse(data=ActivityGroupCounts(**result))
    except Exception as exc:
        logger.exception("metrics.activity_groups unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Activity groups unavailable") from exc
    finally:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("metrics.activity_groups completed elapsed_ms=%s", elapsed_ms)


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
    guild_id = resolve_guild_id(current_user)

    try:
        result = await internal_api.get_metrics_user(guild_id, user_id, days=days)

        raw_user_id = result.get("user_id")
        result["user_id"] = str(raw_user_id if raw_user_id is not None else user_id)

        for tier_key in ("voice_tier", "chat_tier", "game_tier", "combined_tier"):
            result[tier_key] = result.get(tier_key) or "inactive"

        return UserMetricsResponse(data=UserMetrics(**result))
    except Exception as exc:
        logger.exception("User metrics fetch failed", exc_info=exc)
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
    guild_id = resolve_guild_id(current_user)
    admin_user_id = int(current_user.user_id)

    try:
        result = await internal_api.delete_metrics_user(guild_id, user_id)
        await log_admin_action(
            admin_user_id=admin_user_id,
            guild_id=guild_id,
            action="DELETE_USER_METRICS",
            target_user_id=user_id,
            details={"result": result},
            status="success",
        )
        return result
    except Exception as exc:
        logger.exception("Delete user metrics failed", exc_info=exc)
        with contextlib.suppress(Exception):
            await log_admin_action(
                admin_user_id=admin_user_id,
                guild_id=guild_id,
                action="DELETE_USER_METRICS",
                target_user_id=user_id,
                details={"error_type": type(exc).__name__},
                status="error",
            )
        raise HTTPException(status_code=502, detail="Failed to delete user metrics")
