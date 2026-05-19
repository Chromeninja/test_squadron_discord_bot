"""Health and system monitoring schemas."""

from pydantic import BaseModel


class SystemMetrics(BaseModel):
    """System resource metrics."""

    cpu_percent: float
    memory_percent: float


class HealthOverview(BaseModel):
    """Bot health overview for dashboard."""

    status: str  # "healthy", "degraded", "unhealthy"
    uptime_seconds: int
    db_ok: bool
    discord_latency_ms: float | None = None
    system: SystemMetrics


class HealthResponse(BaseModel):
    """Response for /api/health/overview."""

    success: bool = True
    data: HealthOverview
