"""
Health monitoring routes for admin dashboard.

Provides endpoints for checking bot health, system metrics, and status.
"""

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_any,
    translate_internal_api_error,
)
from core.schemas import HealthOverview, HealthResponse, SystemMetrics
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/overview", response_model=HealthResponse, dependencies=[Depends(require_any("admin"))])
async def get_health_overview(
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get comprehensive bot health overview (admin only).
    
    Returns:
    - Bot status (healthy/degraded/unhealthy)
    - Uptime in seconds
    - Database connectivity
    - Discord gateway latency
    - System resource usage (CPU%, RAM%)
    
    Requires: Admin role
    """
    try:
        report = await internal_api.get_health_report()

        health_overview = HealthOverview(
            status=report["status"],
            uptime_seconds=report["uptime_seconds"],
            db_ok=report["db_ok"],
            discord_latency_ms=report.get("discord_latency_ms"),
            system=SystemMetrics(**report["system"])
        )

        return HealthResponse(data=health_overview)

    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to fetch health report")
