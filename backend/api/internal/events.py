"""Internal API routes for managed events — DB-backed, API key protected.

These routes replace the event-related portions of services/internal_api.py
for the DB layer. They do NOT proxy Discord gateway data.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.api_key import require_bot_api_key
from backend.db.repository.events import EventRepository

router = APIRouter(prefix="/internal", tags=["internal-events"])
logger = logging.getLogger(__name__)


def get_event_repository() -> EventRepository:
    """Provide an EventRepository. Override in tests via dependency_overrides.

    The repository is stateless (it opens a connection per call via
    Database.get_connection()), so a fresh instance per request is cheap.
    """
    return EventRepository()


@router.get("/guilds/{guild_id}/managed-events")
async def list_managed_events(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Return all non-deleted managed events for a guild."""
    events = await repo.get_managed_events(guild_id)
    return {"events": events}


@router.get("/guilds/{guild_id}/managed-events/pending-sync")
async def list_pending_sync_events(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Return managed events with pending sync status for a guild."""
    events = await repo.get_pending_sync(guild_id)
    return {"events": events}


@router.get("/guilds/{guild_id}/managed-events/{event_id}")
async def get_managed_event(
    guild_id: int,
    event_id: int,
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Return a single managed event by local DB ID."""
    event = await repo.get_managed_event(guild_id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Managed event not found")
    return {"event": event}


@router.post("/guilds/{guild_id}/managed-events")
async def create_managed_event(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Create a new managed event row."""
    created_by_user_id: str | None = payload.pop("created_by_user_id", None)
    created_by_name: str | None = payload.pop("created_by_name", None)
    event = await repo.create(
        guild_id=guild_id,
        event_data=payload,
        created_by_user_id=created_by_user_id,
        created_by_name=created_by_name,
    )
    return {"event": event}


@router.patch("/guilds/{guild_id}/managed-events/{event_id}")
async def update_managed_event(
    guild_id: int,
    event_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Update fields on a managed event."""
    updated_by_user_id: str | None = payload.pop("updated_by_user_id", None)
    updated_by_name: str | None = payload.pop("updated_by_name", None)
    event = await repo.update(
        guild_id=guild_id,
        event_id=event_id,
        event_data=payload,
        updated_by_user_id=updated_by_user_id,
        updated_by_name=updated_by_name,
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Managed event not found")
    return {"event": event}


@router.delete("/guilds/{guild_id}/managed-events/{event_id}")
async def delete_managed_event(
    guild_id: int,
    event_id: int,
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Soft-delete a managed event."""
    deleted = await repo.delete(guild_id=guild_id, event_id=event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Managed event not found")
    return {"success": True}


@router.post("/guilds/{guild_id}/managed-events/upsert-from-discord")
async def upsert_from_discord(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: EventRepository = Depends(get_event_repository),
) -> dict[str, Any]:
    """Upsert a managed event from a Discord event payload."""
    event = await repo.upsert_from_discord(guild_id=guild_id, event_data=payload)
    return {"event": event}
