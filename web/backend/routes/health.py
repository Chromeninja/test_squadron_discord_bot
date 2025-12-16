"""
Health monitoring routes for admin dashboard.

Provides endpoints for checking bot health, system metrics, and status.
Includes config validation status, cog health, and HTTP client metrics.
"""

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_bot_admin,
    translate_internal_api_error,
)
from core.schemas import HealthOverview, HealthResponse, SystemMetrics
from fastapi import APIRouter, Depends, HTTPException

from config.config_loader import ConfigLoader

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/")
async def health_check():
    """
    Simple health check endpoint (public).

    Returns basic service status without requiring authentication.
    Use /overview for detailed health metrics (admin only).
    """
    return {
        "status": "ok",
        "service": "test-squadron-backend",
        "config_loaded": bool(ConfigLoader._config),
    }


@router.get(
    "/overview",
    response_model=HealthResponse,
    dependencies=[Depends(require_bot_admin())],
)
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
            system=SystemMetrics(**report["system"]),
        )

        return HealthResponse(data=health_overview)

    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to fetch health report")


@router.get("/config-status")
async def get_config_status():
    """
    Get configuration loading status for observability.

    Returns:
        - config_status: "ok" | "degraded" | "error" | "not_loaded"
        - config_path: Path that was loaded
        - config_loaded: Boolean indicating if config has any values

    No authentication required (safe operational endpoint).
    """
    return ConfigLoader.get_config_status()


@router.get("/readiness")
async def readiness_check():
    """
    Kubernetes-style readiness probe.

    Checks if the backend is ready to receive traffic:
    - Config loaded (at least degraded mode)
    - Database connection pool initialized

    Returns 200 if ready, 503 if not.
    """
    config_status = ConfigLoader.get_config_status()

    # Config must not be in an error/not_loaded state
    status_value = config_status["config_status"]

    if status_value in ("not_loaded", "error"):
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "reason": "Configuration not loaded"
                if status_value == "not_loaded"
                else "Configuration failed to load",
                "config_status": status_value,
            },
        )

    return {
        "ready": True,
        "config_status": status_value,
        "config_path": config_status.get("config_path"),
    }


@router.get("/liveness")
async def liveness_check():
    """
    Kubernetes-style liveness probe.

    Simple check that the application is running.
    Returns 200 if alive.
    """
    return {"alive": True}
