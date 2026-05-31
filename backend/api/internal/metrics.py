"""Internal API routes for metrics — DB-backed, API key protected.

These routes provide read access to guild metrics and a GDPR erasure endpoint.
They delegate to the existing metrics_queries module and MetricsService.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.auth.api_key import require_bot_api_key

import services.metrics_queries as _queries

router = APIRouter(prefix="/internal", tags=["internal-metrics"])
logger = logging.getLogger(__name__)


@router.get("/guilds/{guild_id}/metrics/overview")
async def get_metrics_overview(
    guild_id: int,
    days: int = Query(default=7, ge=1, le=365),
    user_ids: list[int] = Query(default=[]),
    _: str = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Return aggregated metrics overview for a guild."""
    uid_filter = user_ids if user_ids else None
    result = await _queries.get_guild_metrics(guild_id, days=days, user_ids=uid_filter)
    return result


@router.get("/guilds/{guild_id}/metrics/voice/leaderboard")
async def get_voice_leaderboard(
    guild_id: int,
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    user_ids: list[int] = Query(default=[]),
    _: str = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Return top users by voice time for a guild."""
    uid_filter = user_ids if user_ids else None
    results = await _queries.get_voice_leaderboard(
        guild_id, days=days, limit=limit, user_ids=uid_filter
    )
    return {"leaderboard": results}


@router.get("/guilds/{guild_id}/metrics/messages/leaderboard")
async def get_message_leaderboard(
    guild_id: int,
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    user_ids: list[int] = Query(default=[]),
    _: str = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Return top users by message count for a guild."""
    uid_filter = user_ids if user_ids else None
    results = await _queries.get_message_leaderboard(
        guild_id, days=days, limit=limit, user_ids=uid_filter
    )
    return {"leaderboard": results}


@router.get("/guilds/{guild_id}/metrics/activity-groups")
async def get_activity_groups(
    guild_id: int,
    days: int = Query(default=30, ge=1, le=365),
    _: str = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Return activity tier counts per dimension for a guild.

    NOTE: This endpoint requires a live MetricsService instance (which holds
    in-memory session state). It is a stub that returns a placeholder until
    the MetricsService dependency injection pattern is finalised for the
    backend process. The bot process should use its service container instead.
    """
    logger.warning(
        "GET /internal/guilds/%s/metrics/activity-groups called without MetricsService; "
        "returning empty response. Wire up MetricsService via dependency injection.",
        guild_id,
    )
    return {
        "days": days,
        "counts": {},
        "note": (
            "activity-groups requires MetricsService (which holds gateway state). "
            "Query via the bot's internal API instead."
        ),
    }


@router.delete("/guilds/{guild_id}/metrics/user/{user_id}")
async def delete_user_metrics(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """GDPR erasure: delete all metrics data for a user in a guild.

    NOTE: Full erasure (including in-memory buffers) requires a live
    MetricsService. This route handles the persistent DB layer only via
    direct SQL. For complete erasure, also call the bot process endpoint.
    """
    from services.db.metrics_db import MetricsDatabase

    deleted: dict[str, int] = {}
    try:
        async with MetricsDatabase.get_connection() as db:
            for table in (
                "voice_sessions",
                "game_sessions",
                "message_counts",
                "metrics_user_hourly",
            ):
                cursor = await db.execute(
                    f"DELETE FROM {table} WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                deleted[table] = cursor.rowcount
            await db.commit()
    except Exception as exc:
        logger.error(
            "Failed to delete metrics for user %s in guild %s: %s",
            user_id,
            guild_id,
            exc,
        )
        raise

    return {"deleted_rows": deleted, "user_id": user_id, "guild_id": guild_id}
