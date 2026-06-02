"""Internal API routes for tickets — DB-backed, API key protected.

These routes provide CRUD operations on the tickets, ticket_categories,
and ticket_channel_configs tables, accessed by the bot connector and
tested with mocked repositories.
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


# ------------------------------------------------------------------
# Ticket Categories
# ------------------------------------------------------------------


@router.get("/guilds/{guild_id}/ticket-categories")
async def list_categories(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return all ticket categories for a guild."""
    categories = await repo.get_categories(guild_id)
    return {"categories": categories}


@router.post("/guilds/{guild_id}/ticket-categories")
async def create_category(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Create a new ticket category."""
    cat_id = await repo.create_category(
        guild_id=guild_id,
        name=payload.get("name", ""),
        description=payload.get("description", ""),
        welcome_message=payload.get("welcome_message", ""),
        role_ids=payload.get("role_ids"),
        prerequisite_role_ids_all=payload.get("prerequisite_role_ids_all"),
        prerequisite_role_ids_any=payload.get("prerequisite_role_ids_any"),
        emoji=payload.get("emoji"),
        channel_id=payload.get("channel_id", 0),
    )
    if cat_id is None:
        raise HTTPException(status_code=422, detail="Failed to create category")
    category = await repo.get_category(cat_id)
    if category is None:
        raise HTTPException(status_code=422, detail="Failed to fetch created category")
    return {"category": category}


@router.get("/guilds/{guild_id}/ticket-categories/{category_id}")
async def get_category(
    guild_id: int,
    category_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return a single category by ID."""
    category = await repo.get_category(category_id)
    if category is None or category.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"category": category}


@router.patch("/guilds/{guild_id}/ticket-categories/{category_id}")
async def update_category(
    guild_id: int,
    category_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Update fields on a category."""
    category = await repo.get_category(category_id)
    if category is None or category.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Category not found")
    updated = await repo.update_category(category_id, **payload)
    if not updated:
        raise HTTPException(status_code=422, detail="Failed to update category")
    updated_cat = await repo.get_category(category_id)
    return {"category": updated_cat}


@router.delete("/guilds/{guild_id}/ticket-categories/{category_id}")
async def delete_category(
    guild_id: int,
    category_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Delete a ticket category."""
    category = await repo.get_category(category_id)
    if category is None or category.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Category not found")
    deleted = await repo.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=422, detail="Failed to delete category")
    return {"success": True}


# ------------------------------------------------------------------
# Channel Configs
# ------------------------------------------------------------------


@router.get("/guilds/{guild_id}/ticket-channels")
async def list_channel_configs(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return all channel configs for a guild."""
    configs = await repo.get_channel_configs(guild_id)
    return {"configs": configs}


@router.post("/guilds/{guild_id}/ticket-channels")
async def create_channel_config(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Create a new channel config."""
    config_id = await repo.create_channel_config(
        guild_id=guild_id,
        channel_id=payload.get("channel_id", 0),
        panel_title=payload.get("panel_title"),
        panel_description=payload.get("panel_description"),
        panel_color=payload.get("panel_color"),
        button_text=payload.get("button_text"),
        button_emoji=payload.get("button_emoji"),
        enable_public_button=payload.get("enable_public_button"),
        public_button_text=payload.get("public_button_text"),
        public_button_emoji=payload.get("public_button_emoji"),
        private_button_color=payload.get("private_button_color"),
        public_button_color=payload.get("public_button_color"),
        button_order=payload.get("button_order"),
    )
    if config_id is None:
        raise HTTPException(status_code=422, detail="Failed to create channel config")
    config = await repo.get_channel_config(guild_id, payload.get("channel_id", 0))
    if config is None:
        raise HTTPException(status_code=422, detail="Failed to fetch created config")
    return {"config": config}


@router.get("/guilds/{guild_id}/ticket-channels/{channel_id}")
async def get_channel_config(
    guild_id: int,
    channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return a channel config."""
    config = await repo.get_channel_config(guild_id, channel_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Channel config not found")
    return {"config": config}


@router.patch("/guilds/{guild_id}/ticket-channels/{channel_id}")
async def update_channel_config(
    guild_id: int,
    channel_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Update a channel config."""
    config = await repo.get_channel_config(guild_id, channel_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Channel config not found")
    updated = await repo.update_channel_config(
        guild_id=guild_id,
        channel_id=channel_id,
        new_channel_id=payload.get("new_channel_id"),
        panel_title=payload.get("panel_title"),
        panel_description=payload.get("panel_description"),
        panel_color=payload.get("panel_color"),
        button_text=payload.get("button_text"),
        button_emoji=payload.get("button_emoji"),
        enable_public_button=payload.get("enable_public_button"),
        public_button_text=payload.get("public_button_text"),
        public_button_emoji=payload.get("public_button_emoji"),
        private_button_color=payload.get("private_button_color"),
        public_button_color=payload.get("public_button_color"),
        button_order=payload.get("button_order"),
    )
    if not updated:
        raise HTTPException(status_code=422, detail="Failed to update channel config")
    updated_config = await repo.get_channel_config(
        guild_id, payload.get("new_channel_id", channel_id)
    )
    return {"config": updated_config}


@router.delete("/guilds/{guild_id}/ticket-channels/{channel_id}")
async def delete_channel_config(
    guild_id: int,
    channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Delete a channel config."""
    config = await repo.get_channel_config(guild_id, channel_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Channel config not found")
    deleted = await repo.delete_channel_config(guild_id, channel_id)
    if not deleted:
        raise HTTPException(status_code=422, detail="Failed to delete channel config")
    return {"success": True}


# ------------------------------------------------------------------
# Ticket Queries & Actions
# ------------------------------------------------------------------


@router.get("/guilds/{guild_id}/tickets/stats")
async def get_ticket_stats(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return ticket statistics for a guild."""
    stats = await repo.get_ticket_stats(guild_id)
    return {"stats": stats}


@router.get("/guilds/{guild_id}/tickets/by-thread/{thread_id}")
async def get_ticket_by_thread(
    guild_id: int,
    thread_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return a ticket by thread ID."""
    ticket = await repo.get_ticket_by_thread(thread_id)
    if ticket is None or ticket.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": ticket}


@router.post("/guilds/{guild_id}/tickets/by-thread/{thread_id}/claim")
async def claim_ticket(
    guild_id: int,
    thread_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Claim a ticket."""
    ticket = await repo.get_ticket_by_thread(thread_id)
    if ticket is None or ticket.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    claimed_by = payload.get("claimed_by")
    if claimed_by is None:
        raise HTTPException(status_code=422, detail="claimed_by required")
    claimed = await repo.claim_ticket(thread_id, claimed_by)
    return {"claimed": claimed}


@router.post("/guilds/{guild_id}/tickets/by-thread/{thread_id}/unclaim")
async def unclaim_ticket(
    guild_id: int,
    thread_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Unclaim a ticket."""
    ticket = await repo.get_ticket_by_thread(thread_id)
    if ticket is None or ticket.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    unclaimed = await repo.unclaim_ticket(thread_id)
    return {"unclaimed": unclaimed}


@router.post("/guilds/{guild_id}/tickets/by-thread/{thread_id}/reopen")
async def reopen_ticket(
    guild_id: int,
    thread_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Reopen a ticket."""
    ticket = await repo.get_ticket_by_thread(thread_id)
    if ticket is None or ticket.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    reopened_by = payload.get("reopened_by")
    if reopened_by is None:
        raise HTTPException(status_code=422, detail="reopened_by required")
    reopened = await repo.reopen_ticket(thread_id, reopened_by)
    return {"reopened": reopened}


@router.post("/guilds/{guild_id}/tickets/by-thread/{thread_id}/close")
async def close_by_thread(
    guild_id: int,
    thread_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Close a ticket by thread ID."""
    ticket = await repo.get_ticket_by_thread(thread_id)
    if ticket is None or ticket.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    closed_by = payload.get("closed_by")
    if closed_by is None:
        raise HTTPException(status_code=422, detail="closed_by required")
    closed = await repo.close_ticket_by_thread(
        thread_id, closed_by, payload.get("close_reason")
    )
    return {"closed": closed}


@router.post("/guilds/{guild_id}/tickets/by-thread/{thread_id}/mark-deleted")
async def mark_deleted(
    guild_id: int,
    thread_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Mark a ticket thread as deleted."""
    ticket = await repo.get_ticket_by_thread(thread_id)
    if ticket is None or ticket.get("guild_id") != guild_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    marked = await repo.mark_thread_deleted(thread_id)
    return {"marked": marked}


# ------------------------------------------------------------------
# Ticket Queries (Additional)
# ------------------------------------------------------------------


@router.get("/guilds/{guild_id}/tickets/open")
async def list_open_tickets(
    guild_id: int,
    user_id: int | None = None,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return open tickets for a guild, optionally filtered by user."""
    tickets = await repo.get_open_tickets(guild_id, user_id)
    return {"tickets": tickets}


@router.get("/guilds/{guild_id}/ticket-categories/by-channel/{channel_id}")
async def list_categories_for_channel(
    guild_id: int,
    channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return ticket categories assigned to a specific channel."""
    categories = await repo.get_categories_for_channel(guild_id, channel_id)
    return {"categories": categories}


@router.get("/guilds/{guild_id}/tickets/thread-health")
async def get_thread_health(
    guild_id: int,
    thread_limit: int = 1000,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return thread usage data for a guild (active/archived/deleted counts + usage status)."""
    health = await repo.get_thread_health(guild_id, thread_limit)
    return {"health": health}


@router.get("/guilds/{guild_id}/tickets/oldest-closed")
async def get_oldest_closed(
    guild_id: int,
    limit: int = 5,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return the oldest closed tickets that still have threads."""
    tickets = await repo.get_oldest_closed_tickets(guild_id, limit)
    return {"tickets": tickets}


@router.get("/guilds/{guild_id}/tickets/cleanup-candidates")
async def get_cleanup_candidates(
    guild_id: int,
    older_than_days: int,
    limit: int | None = None,
    _: str = Depends(require_bot_api_key),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict[str, Any]:
    """Return closed tickets older than older_than_days (min 30-day safety buffer)."""
    tickets = await repo.get_cleanup_candidates(guild_id, older_than_days, limit)
    return {"tickets": tickets}
