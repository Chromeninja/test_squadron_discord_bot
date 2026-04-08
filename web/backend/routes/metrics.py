"""
Metrics endpoints for the dashboard.

Provides aggregated user activity metrics: voice time, game tracking,
message counts, leaderboards, and time-series data for charting.
"""

import asyncio
import contextlib
import logging
import time

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_discord_manager,
)
from core.pagination import is_all_guilds_mode
from core.schemas import (
    ActivityGroupCounts,
    ActivityGroupCountsResponse,
    DashboardMetricsBundle,
    DashboardMetricsResponse,
    GameMetrics,
    GameMetricsResponse,
    LeaderboardResponse,
    MessageLeaderboardEntry,
    MetricsOverview,
    MetricsOverviewResponse,
    TimeSeriesResponse,
    TopGamesResponse,
    UserMetrics,
    UserMetricsResponse,
    UserProfile,
    VoiceLeaderboardEntry,
)
from fastapi import APIRouter, Depends, HTTPException, Query

from helpers.audit import log_admin_action

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_GAME_DETAIL_FILTER_USERS = 1000


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
        return sorted(merged_user_ids)
    except Exception as exc:
        logger.warning(
            "Failed to resolve activity filter",
            exc_info=exc,
        )
        return []


def _coerce_metric_value(raw_value: object) -> int | None:
    """
    Coerce leaderboard metric values to integers when possible.

    AI Notes:
        Leaderboard metrics are expected to be numeric counts/durations, but
        upstream payloads may occasionally contain loosely typed values in the
        generic ``value`` field. The boolean case is defensive normalization so
        unexpected ``true``/``false`` values become ``1``/``0`` instead of
        being rejected during response shaping.
    """
    if isinstance(raw_value, bool):
        # Defensive handling for inconsistent upstream payloads; booleans are
        # not an expected leaderboard metric type, but some serializers may
        # emit them in the generic "value" field.
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        with contextlib.suppress(ValueError):
            return int(float(raw_value))
    return None


def _normalize_leaderboard_entries(
    entries: list[object],
    *,
    metric_field: str,
) -> list[dict[str, object]]:
    """Normalize leaderboard payloads for stable frontend consumption."""
    normalized_entries: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized = dict(entry)
        if "user_id" in normalized:
            normalized["user_id"] = str(normalized["user_id"])
        if metric_field not in normalized and "value" in normalized:
            coerced_value = _coerce_metric_value(normalized.get("value"))
            if coerced_value is not None:
                normalized[metric_field] = coerced_value
        normalized.pop("value", None)
        normalized_entries.append(normalized)
    return normalized_entries


def _normalize_timeseries_data(data: list[object]) -> list[dict[str, object]]:
    """Filter timeseries payloads down to dict items for response stability."""
    return [dict(item) for item in data if isinstance(item, dict)]


def _build_voice_leaderboard_entries(
    entries: list[object],
) -> list[VoiceLeaderboardEntry]:
    """Build typed voice leaderboard entries for the bundled response."""
    typed_entries: list[VoiceLeaderboardEntry] = []
    for entry in _normalize_leaderboard_entries(entries, metric_field="total_seconds"):
        total_seconds = _coerce_metric_value(entry.get("total_seconds"))
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


def _build_message_leaderboard_entries(
    entries: list[object],
) -> list[MessageLeaderboardEntry]:
    """Build typed message leaderboard entries for the bundled response."""
    typed_entries: list[MessageLeaderboardEntry] = []
    for entry in _normalize_leaderboard_entries(entries, metric_field="total_messages"):
        total_messages = _coerce_metric_value(entry.get("total_messages"))
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
    started_at = time.perf_counter()

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
    guild_id = _resolve_guild_id(current_user)
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
                voice_leaderboard=_build_voice_leaderboard_entries(
                    voice_result.get("entries", [])
                ),
                message_leaderboard=_build_message_leaderboard_entries(
                    message_result.get("entries", [])
                ),
                top_games=top_games_result.get("games", []),
                message_timeseries=_normalize_timeseries_data(
                    message_timeseries_result.get("data", [])
                ),
                voice_timeseries=_normalize_timeseries_data(
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
    guild_id = _resolve_guild_id(current_user)

    try:
        user_ids = await _resolve_activity_filter(
            internal_api, guild_id, dimension, tier, days=days
        )
        result = await internal_api.get_metrics_voice_leaderboard(
            guild_id, days=days, limit=limit, user_ids=user_ids
        )
        normalized_entries = _normalize_leaderboard_entries(
            result.get("entries", []), metric_field="total_seconds"
        )
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
        normalized_entries = _normalize_leaderboard_entries(
            result.get("entries", []), metric_field="total_messages"
        )
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
    guild_id = _resolve_guild_id(current_user)

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
    except Exception:
        raise HTTPException(status_code=502, detail="Game metrics unavailable")


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
    except Exception:
        raise HTTPException(status_code=502, detail="Timeseries unavailable")
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
    guild_id = _resolve_guild_id(current_user)
    started_at = time.perf_counter()

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
    guild_id = _resolve_guild_id(current_user)

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
    guild_id = _resolve_guild_id(current_user)
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
