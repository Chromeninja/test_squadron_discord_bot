"""Health and metrics endpoints.

GET /api/v1/health  — liveness + dependency status
GET /api/v1/metrics — Prometheus-format metrics (stub; expand with prometheus_client later)
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from backend.auth.api_key import require_bot_api_key
from services.db.database import Database

router = APIRouter(tags=["health"])

# Track startup time for uptime reporting
_START_TIME = time.time()


@router.get("/api/v1/health")
async def health_check() -> dict:
    """Return service health including database connectivity."""
    db_ok = False
    try:
        # Lightweight ping — just check we can open a connection
        async with Database.get_connection() as db:
            await db.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "uptime_seconds": int(time.time() - _START_TIME),
    }


@router.get(
    "/api/v1/metrics", response_class=PlainTextResponse, include_in_schema=False
)
async def metrics(_: str = Depends(require_bot_api_key)) -> str:
    """Prometheus-format metrics endpoint (stub — expand with prometheus_client)."""
    uptime = int(time.time() - _START_TIME)
    return (
        "# HELP process_uptime_seconds Seconds since the backend started\n"
        "# TYPE process_uptime_seconds gauge\n"
        f"process_uptime_seconds {uptime}\n"
    )
