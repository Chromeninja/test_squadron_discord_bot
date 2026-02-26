"""
Ticket management API endpoints.

Provides CRUD for ticket categories, ticket listing/stats, and
guild-level ticket settings — all scoped to the active guild.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.dependencies import (
    InternalAPIClient,
    get_config_service,
    get_internal_api_client,
    require_discord_manager,
    require_staff,
    translate_internal_api_error,
)
from core.schemas import (
    TicketCategory,
    TicketCategoryCreate,
    TicketCategoryListResponse,
    TicketCategoryUpdate,
    TicketInfo,
    TicketListResponse,
    TicketSettings,
    TicketSettingsResponse,
    TicketSettingsUpdate,
    TicketStatsResponse,
    UserProfile,
)
from core.validation import ensure_active_guild
from fastapi import APIRouter, Depends, HTTPException, Query

from services.ticket_service import TicketService
from utils.logging import get_logger

if TYPE_CHECKING:
    from services.config_service import ConfigService

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ticket_service: TicketService | None = None


def _get_ticket_service() -> TicketService:
    """Lazy-singleton for TicketService in the backend process."""
    global _ticket_service
    if _ticket_service is None:
        _ticket_service = TicketService()
        _ticket_service._initialized = True  # schema already applied by bot
    return _ticket_service


def _build_category_list(cats: list[dict]) -> TicketCategoryListResponse:
    """Build a ``TicketCategoryListResponse`` from service dicts.

    Single source of truth for category → Pydantic serialisation.
    """
    items = [
        TicketCategory(
            id=c["id"],
            guild_id=str(c["guild_id"]),
            name=c["name"],
            description=c.get("description", ""),
            welcome_message=c.get("welcome_message", ""),
            role_ids=[str(r) for r in c.get("role_ids", [])],
            emoji=c.get("emoji"),
            sort_order=c.get("sort_order", 0),
            created_at=c.get("created_at", 0),
        )
        for c in cats
    ]
    return TicketCategoryListResponse(categories=items)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=TicketCategoryListResponse)
async def list_categories(
    current_user: UserProfile = Depends(require_staff()),
) -> TicketCategoryListResponse:
    """List all ticket categories for the active guild."""
    guild_id = ensure_active_guild(current_user)
    svc = _get_ticket_service()
    cats = await svc.get_categories(guild_id)
    return _build_category_list(cats)


@router.post("/categories", response_model=TicketCategoryListResponse, status_code=201)
async def create_category(
    body: TicketCategoryCreate,
    current_user: UserProfile = Depends(require_discord_manager()),
) -> TicketCategoryListResponse:
    """Create a new ticket category."""
    guild_id = ensure_active_guild(current_user)
    # Ensure the body guild_id matches the active guild
    if str(guild_id) != body.guild_id:
        raise HTTPException(status_code=403, detail="Guild mismatch")

    svc = _get_ticket_service()
    cat_id = await svc.create_category(
        guild_id=guild_id,
        name=body.name,
        description=body.description,
        welcome_message=body.welcome_message,
        role_ids=[int(r) for r in body.role_ids],
        emoji=body.emoji,
    )
    if cat_id is None:
        raise HTTPException(status_code=500, detail="Failed to create category")

    # Return updated list
    cats = await svc.get_categories(guild_id)
    return _build_category_list(cats)


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: TicketCategoryUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
) -> dict:
    """Update a ticket category."""
    ensure_active_guild(current_user)
    svc = _get_ticket_service()

    # Build kwargs from non-None fields
    kwargs: dict = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.description is not None:
        kwargs["description"] = body.description
    if body.welcome_message is not None:
        kwargs["welcome_message"] = body.welcome_message
    if body.role_ids is not None:
        kwargs["role_ids"] = [int(r) for r in body.role_ids]
    if body.emoji is not None:
        kwargs["emoji"] = body.emoji
    if body.sort_order is not None:
        kwargs["sort_order"] = body.sort_order

    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await svc.update_category(category_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Category not found")

    return {"success": True}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    current_user: UserProfile = Depends(require_discord_manager()),
) -> dict:
    """Delete a ticket category."""
    ensure_active_guild(current_user)
    svc = _get_ticket_service()
    deleted = await svc.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True}


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@router.get("/list", response_model=TicketListResponse)
async def list_tickets(
    status: str | None = Query(None, pattern="^(open|closed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserProfile = Depends(require_staff()),
) -> TicketListResponse:
    """List tickets for the active guild with optional status filter."""
    guild_id = ensure_active_guild(current_user)
    svc = _get_ticket_service()

    offset = (page - 1) * page_size
    tickets = await svc.get_tickets(guild_id, status=status, limit=page_size, offset=offset)
    total = await svc.get_ticket_count(guild_id, status=status)

    items = [
        TicketInfo(
            id=t["id"],
            guild_id=str(t["guild_id"]),
            channel_id=str(t["channel_id"]),
            thread_id=str(t["thread_id"]),
            user_id=str(t["user_id"]),
            category_id=t.get("category_id"),
            status=t["status"],
            closed_by=str(t["closed_by"]) if t.get("closed_by") else None,
            created_at=t.get("created_at", 0),
            closed_at=t.get("closed_at"),
            claimed_by=str(t["claimed_by"]) if t.get("claimed_by") else None,
            claimed_at=t.get("claimed_at"),
            close_reason=t.get("close_reason"),
            initial_description=t.get("initial_description"),
            reopened_at=t.get("reopened_at"),
            reopened_by=str(t["reopened_by"]) if t.get("reopened_by") else None,
        )
        for t in tickets
    ]
    return TicketListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/stats", response_model=TicketStatsResponse)
async def ticket_stats(
    current_user: UserProfile = Depends(require_staff()),
) -> TicketStatsResponse:
    """Get ticket statistics for the active guild."""
    guild_id = ensure_active_guild(current_user)
    svc = _get_ticket_service()
    data = await svc.get_ticket_stats(guild_id)
    return TicketStatsResponse(
        open=data["open"],
        closed=data["closed"],
        total=data["total"],
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=TicketSettingsResponse)
async def get_settings(
    current_user: UserProfile = Depends(require_discord_manager()),
    config: ConfigService = Depends(get_config_service),
) -> TicketSettingsResponse:
    """Retrieve ticket settings for the active guild."""
    guild_id = ensure_active_guild(current_user)

    channel_id = await config.get_guild_setting(guild_id, "tickets.channel_id")
    panel_message_id = await config.get_guild_setting(guild_id, "tickets.panel_message_id")
    panel_title = await config.get_guild_setting(guild_id, "tickets.panel_title")
    panel_description = await config.get_guild_setting(guild_id, "tickets.panel_description")
    log_channel_id = await config.get_guild_setting(guild_id, "tickets.log_channel_id")
    close_message = await config.get_guild_setting(guild_id, "tickets.close_message")
    default_welcome = await config.get_guild_setting(guild_id, "tickets.default_welcome_message")
    max_open_per_user = await config.get_guild_setting(
        guild_id, "tickets.max_open_per_user", default="5"
    )
    reopen_window_hours = await config.get_guild_setting(
        guild_id, "tickets.reopen_window_hours", default="48"
    )

    svc = _get_ticket_service()
    staff_roles = await svc.get_staff_role_ids(config, guild_id)

    settings = TicketSettings(
        channel_id=str(channel_id) if channel_id else None,
        panel_message_id=str(panel_message_id) if panel_message_id else None,
        panel_title=panel_title,
        panel_description=panel_description,
        log_channel_id=str(log_channel_id) if log_channel_id else None,
        close_message=close_message,
        staff_roles=[str(r) for r in staff_roles],
        default_welcome_message=default_welcome,
        max_open_per_user=int(max_open_per_user) if max_open_per_user else 5,
        reopen_window_hours=int(reopen_window_hours) if reopen_window_hours else 48,
    )
    return TicketSettingsResponse(settings=settings)


@router.put("/settings")
async def update_settings(
    body: TicketSettingsUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
    config: ConfigService = Depends(get_config_service),
) -> dict:
    """Update ticket settings for the active guild."""
    guild_id = ensure_active_guild(current_user)

    if body.channel_id is not None:
        await config.set_guild_setting(guild_id, "tickets.channel_id", body.channel_id)
    if body.panel_title is not None:
        await config.set_guild_setting(guild_id, "tickets.panel_title", body.panel_title)
    if body.panel_description is not None:
        await config.set_guild_setting(guild_id, "tickets.panel_description", body.panel_description)
    if body.log_channel_id is not None:
        await config.set_guild_setting(guild_id, "tickets.log_channel_id", body.log_channel_id)
    if body.close_message is not None:
        await config.set_guild_setting(guild_id, "tickets.close_message", body.close_message)
    if body.staff_roles is not None:
        await config.set_guild_setting(
            guild_id, "tickets.staff_roles", json.dumps([int(r) for r in body.staff_roles])
        )
    if body.default_welcome_message is not None:
        await config.set_guild_setting(
            guild_id, "tickets.default_welcome_message", body.default_welcome_message
        )
    if body.max_open_per_user is not None:
        await config.set_guild_setting(
            guild_id, "tickets.max_open_per_user", str(body.max_open_per_user)
        )
    if body.reopen_window_hours is not None:
        await config.set_guild_setting(
            guild_id, "tickets.reopen_window_hours", str(body.reopen_window_hours)
        )

    return {"success": True}


# ---------------------------------------------------------------------------
# Deploy / refresh panel (triggers bot via internal API)
# ---------------------------------------------------------------------------


@router.post("/deploy-panel")
async def deploy_panel(
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> dict:
    """Ask the bot to deploy (or refresh) the ticket panel in the configured channel.

    The dashboard should save settings first via ``PUT /settings``, then call
    this endpoint so the bot sends the embed + button.
    """
    guild_id = ensure_active_guild(current_user)

    try:
        result = await internal_api.deploy_ticket_panel(guild_id)
        return {"success": True, "message_id": result.get("message_id")}
    except Exception as exc:
        logger.exception(
            "Failed to deploy ticket panel for guild %s", guild_id, exc_info=exc
        )
        raise translate_internal_api_error(
            exc,
            "Could not reach the bot to deploy the panel.",
        ) from exc
