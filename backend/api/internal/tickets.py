"""Internal API routes for tickets — DB-backed, API key protected.

These routes provide CRUD operations on the tickets table, accessed
by the bot connector and tested with mocked repositories.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.api_key import require_bot_api_key
from backend.db.repository.tickets import TicketRepository

router = APIRouter(prefix="/internal", tags=["internal-tickets"])
logger = logging.getLogger(__name__)


def get_ticket_repository() -> TicketRepository:
    """Provide a TicketRepository. Override in tests via dependency_overrides.

    The repository is stateless (it opens a connection per call via
    Database.get_connection()), so a fresh instance per request is cheap.
    """
    return TicketRepository()


@router.get("/guilds/{guild_id}/tickets")
async def list_tickets(
    guild_id: int,
    status: str | None = None,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return all non-deleted tickets for a guild, optionally filtered by status."""
    tickets = await repo.get_tickets(guild_id, status)
    return {"tickets": tickets}


@router.post("/guilds/{guild_id}/tickets")
async def create_ticket(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Create a new ticket row.

    Requires channel_id, thread_id, and user_id in the payload.
    """
    try:
        created = await repo.create_ticket(guild_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ticket": created}


@router.get("/guilds/{guild_id}/tickets/{ticket_id}")
async def get_ticket(
    guild_id: int,
    ticket_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return a single ticket by ID."""
    ticket = await repo.get_ticket(guild_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": ticket}


@router.patch("/guilds/{guild_id}/tickets/{ticket_id}")
async def update_ticket(
    guild_id: int,
    ticket_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Update fields on a ticket."""
    updated = await repo.update_ticket(guild_id, ticket_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": updated}


@router.post("/guilds/{guild_id}/tickets/{ticket_id}/close")
async def close_ticket(
    guild_id: int,
    ticket_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Close a ticket with optional closed_by field."""
    closed_by = payload.get("closed_by")
    closed = await repo.close_ticket(guild_id, ticket_id, closed_by=closed_by)
    return {"closed": closed}


@router.delete("/guilds/{guild_id}/tickets/{ticket_id}")
async def delete_ticket(
    guild_id: int,
    ticket_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Soft-delete a ticket."""
    deleted = await repo.delete_ticket(guild_id, ticket_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"success": True}
