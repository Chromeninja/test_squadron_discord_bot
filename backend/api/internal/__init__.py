"""Internal API routers — DB-backed, API key protected."""

from backend.api.internal.events import router as events_router
from backend.api.internal.metrics import router as metrics_router

__all__ = ["events_router", "metrics_router"]
