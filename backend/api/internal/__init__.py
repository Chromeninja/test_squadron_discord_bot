"""Internal API routers — DB-backed, API key protected."""

from backend.api.internal.config import router as config_router
from backend.api.internal.events import router as events_router
from backend.api.internal.metrics import router as metrics_router
from backend.api.internal.tickets import router as tickets_router
from backend.api.internal.verification import router as verification_router
from backend.api.internal.voice import router as voice_router

__all__ = [
    "config_router",
    "events_router",
    "metrics_router",
    "tickets_router",
    "verification_router",
    "voice_router",
]
