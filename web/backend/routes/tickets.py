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
    get_ticket_service,
    require_discord_manager,
    require_staff,
    translate_internal_api_error,
)
from core.schemas import (
    TicketCategory,
    TicketCategoryCreate,
    TicketCategoryListResponse,
    TicketCategoryUpdate,
    TicketChannelConfig,
    TicketChannelConfigCreate,
    TicketChannelConfigListResponse,
    TicketChannelConfigUpdate,
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

from utils.logging import get_logger
from web.backend.routes._ticket_helpers import require_guild_category

if TYPE_CHECKING:
    from services.config_service import ConfigService
    from services.ticket_service import TicketService

logger = get_logger(__name__)

router = APIRouter()


def _parse_role_id_list(field_name: str, raw_role_ids: list[str]) -> list[int]:
    """Parse role ID list from API payload and raise 422 on invalid values."""
    parsed: list[int] = []
    for raw_role_id in raw_role_ids:
        try:
            role_id = int(raw_role_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid role ID in {field_name}",
            ) from exc
        if role_id <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid role ID in {field_name}",
            )
        parsed.append(role_id)
    return parsed


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
            prerequisite_role_ids_all=[
                str(role_id)
                for role_id in c.get("prerequisite_role_ids_all", [])
            ],
            prerequisite_role_ids_any=[
                str(role_id)
                for role_id in c.get("prerequisite_role_ids_any", [])
            ],
            emoji=c.get("emoji"),
            sort_order=c.get("sort_order", 0),
            created_at=c.get("created_at", 0),
            channel_id=str(c.get("channel_id", 0)),
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
    svc: TicketService = Depends(get_ticket_service),
) -> TicketCategoryListResponse:
    """List all ticket categories for the active guild."""
    guild_id = ensure_active_guild(current_user)
    cats = await svc.get_categories(guild_id)
    return _build_category_list(cats)


@router.post("/categories", response_model=TicketCategoryListResponse, status_code=201)
async def create_category(
    body: TicketCategoryCreate,
    current_user: UserProfile = Depends(require_discord_manager()),
    svc: TicketService = Depends(get_ticket_service),
) -> TicketCategoryListResponse:
    """Create a new ticket category."""
    guild_id = ensure_active_guild(current_user)
    # Ensure the body guild_id matches the active guild
    if str(guild_id) != body.guild_id:
        raise HTTPException(status_code=403, detail="Guild mismatch")
    cat_id = await svc.create_category(
        guild_id=guild_id,
        name=body.name,
        description=body.description,
        welcome_message=body.welcome_message,
        role_ids=_parse_role_id_list("role_ids", body.role_ids),
        prerequisite_role_ids_all=_parse_role_id_list(
            "prerequisite_role_ids_all",
            body.prerequisite_role_ids_all,
        ),
        prerequisite_role_ids_any=_parse_role_id_list(
            "prerequisite_role_ids_any",
            body.prerequisite_role_ids_any,
        ),
        emoji=body.emoji,
        channel_id=int(body.channel_id) if body.channel_id else 0,
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
    svc: TicketService = Depends(get_ticket_service),
) -> dict:
    """Update a ticket category."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(svc, category_id, guild_id)

    # Build kwargs from non-None fields
    kwargs: dict[str, object] = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.description is not None:
        kwargs["description"] = body.description
    if body.welcome_message is not None:
        kwargs["welcome_message"] = body.welcome_message
    if body.role_ids is not None:
        kwargs["role_ids"] = _parse_role_id_list("role_ids", body.role_ids)
    if body.prerequisite_role_ids_all is not None:
        kwargs["prerequisite_role_ids_all"] = _parse_role_id_list(
            "prerequisite_role_ids_all",
            body.prerequisite_role_ids_all,
        )
    if body.prerequisite_role_ids_any is not None:
        kwargs["prerequisite_role_ids_any"] = _parse_role_id_list(
            "prerequisite_role_ids_any",
            body.prerequisite_role_ids_any,
        )
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
    svc: TicketService = Depends(get_ticket_service),
) -> dict:
    """Delete a ticket category."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(svc, category_id, guild_id)

    deleted = await svc.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True}


# ---------------------------------------------------------------------------
# Channel Configs (per-channel panel customization)
# ---------------------------------------------------------------------------


def _build_channel_config_list(
    configs: list[dict],
) -> TicketChannelConfigListResponse:
    """Build a ``TicketChannelConfigListResponse`` from service dicts."""
    items = [
        TicketChannelConfig(
            id=c["id"],
            guild_id=str(c["guild_id"]),
            channel_id=str(c["channel_id"]),
            panel_title=c.get("panel_title", "🎫 Support Tickets"),
            panel_description=c.get("panel_description", ""),
            panel_color=c.get("panel_color", "0099FF"),
            button_text=c.get("button_text", "Create Ticket"),
            button_emoji=c.get("button_emoji", "🎫"),
            enable_public_button=bool(c.get("enable_public_button", 0)),
            public_button_text=c.get(
                "public_button_text", "Create Public Ticket"
            ),
            public_button_emoji=c.get("public_button_emoji", "🌐"),
            private_button_color=c.get("private_button_color"),
            public_button_color=c.get("public_button_color"),
            button_order=c.get("button_order", "private_first"),
            sort_order=c.get("sort_order", 0),
            created_at=c.get("created_at", 0),
        )
        for c in configs
    ]
    return TicketChannelConfigListResponse(channels=items)


async def _require_guild_channel_config(
    svc: TicketService, guild_id: int, channel_id: int
) -> dict:
    """Verify a channel config exists and belongs to the given guild.

    Raises ``HTTPException(404)`` on mismatch.
    """
    cfg = await svc.get_channel_config(guild_id, channel_id)
    if cfg is None or cfg["guild_id"] != guild_id:
        raise HTTPException(status_code=404, detail="Channel config not found")
    return cfg


@router.get("/channels", response_model=TicketChannelConfigListResponse)
async def list_channel_configs(
    current_user: UserProfile = Depends(require_staff()),
    svc: TicketService = Depends(get_ticket_service),
) -> TicketChannelConfigListResponse:
    """List all ticket channel configs for the active guild."""
    guild_id = ensure_active_guild(current_user)
    configs = await svc.get_channel_configs(guild_id)
    return _build_channel_config_list(configs)


@router.post(
    "/channels", response_model=TicketChannelConfigListResponse, status_code=201
)
async def create_channel_config(
    body: TicketChannelConfigCreate,
    current_user: UserProfile = Depends(require_discord_manager()),
    svc: TicketService = Depends(get_ticket_service),
) -> TicketChannelConfigListResponse:
    """Create a new ticket channel config."""
    guild_id = ensure_active_guild(current_user)
    # Ensure the body guild_id matches the active guild
    if str(guild_id) != body.guild_id:
        raise HTTPException(status_code=403, detail="Guild mismatch")

    # Check if config already exists
    existing = await svc.get_channel_config(guild_id, int(body.channel_id))
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="Channel config already exists"
        )

    config_id = await svc.create_channel_config(
        guild_id=guild_id,
        channel_id=int(body.channel_id),
        panel_title=body.panel_title,
        panel_description=body.panel_description,
        panel_color=body.panel_color,
        button_text=body.button_text,
        button_emoji=body.button_emoji,
        enable_public_button=body.enable_public_button,
        public_button_text=body.public_button_text,
        public_button_emoji=body.public_button_emoji,
        private_button_color=body.private_button_color,
        public_button_color=body.public_button_color,
        button_order=body.button_order,
    )
    if config_id is None:
        raise HTTPException(
            status_code=500, detail="Failed to create channel config"
        )

    # Return updated list
    configs = await svc.get_channel_configs(guild_id)
    return _build_channel_config_list(configs)


@router.put("/channels/{channel_id}")
async def update_channel_config(
    channel_id: str,
    body: TicketChannelConfigUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
    svc: TicketService = Depends(get_ticket_service),
) -> dict:
    """Update a ticket channel config."""
    guild_id = ensure_active_guild(current_user)
    channel_id_int = int(channel_id)
    await _require_guild_channel_config(svc, guild_id, channel_id_int)

    # Build kwargs from non-None fields
    kwargs: dict = {
        k: v
        for k, v in {
            "new_channel_id": int(body.new_channel_id) if body.new_channel_id else None,
            "panel_title": body.panel_title,
            "panel_description": body.panel_description,
            "panel_color": body.panel_color,
            "button_text": body.button_text,
            "button_emoji": body.button_emoji,
            "enable_public_button": body.enable_public_button,
            "public_button_text": body.public_button_text,
            "public_button_emoji": body.public_button_emoji,
            "private_button_color": body.private_button_color,
            "public_button_color": body.public_button_color,
            "button_order": body.button_order,
        }.items()
        if v is not None
    }

    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = await svc.update_channel_config(
            guild_id, channel_id_int, **kwargs
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Channel config not found")

    return {"success": True}


@router.delete("/channels/{channel_id}")
async def delete_channel_config(
    channel_id: str,
    current_user: UserProfile = Depends(require_discord_manager()),
    svc: TicketService = Depends(get_ticket_service),
) -> dict:
    """Delete a ticket channel config.

    AI Notes:
        This does NOT delete categories assigned to the channel.
        They will become unassigned (channel_id = 0).
    """
    guild_id = ensure_active_guild(current_user)
    channel_id_int = int(channel_id)
    await _require_guild_channel_config(svc, guild_id, channel_id_int)

    deleted = await svc.delete_channel_config(guild_id, channel_id_int)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel config not found")
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
    svc: TicketService = Depends(get_ticket_service),
) -> TicketListResponse:
    """List tickets for the active guild with optional status filter."""
    guild_id = ensure_active_guild(current_user)

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
    svc: TicketService = Depends(get_ticket_service),
) -> TicketStatsResponse:
    """Get ticket statistics for the active guild."""
    guild_id = ensure_active_guild(current_user)
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

    # Fetch all settings in one batch
    _keys = [
        "tickets.channel_id", "tickets.panel_message_id",
        "tickets.log_channel_id", "tickets.close_message",
        "tickets.default_welcome_message",
    ]
    raw: dict[str, str | None] = {}
    for key in _keys:
        raw[key] = await config.get_guild_setting(guild_id, key)
    max_open_per_user = await config.get_guild_setting(
        guild_id, "tickets.max_open_per_user", default="5"
    )
    reopen_window_hours = await config.get_guild_setting(
        guild_id, "tickets.reopen_window_hours", default="48"
    )

    svc = await get_ticket_service()
    staff_roles = await svc.get_staff_role_ids(config, guild_id)

    def _str_or_none(key: str) -> str | None:
        v = raw[key]
        return str(v) if v else None

    settings = TicketSettings(
        channel_id=_str_or_none("tickets.channel_id"),
        panel_message_id=_str_or_none("tickets.panel_message_id"),
        log_channel_id=_str_or_none("tickets.log_channel_id"),
        close_message=raw["tickets.close_message"],
        staff_roles=[str(r) for r in staff_roles],
        default_welcome_message=raw["tickets.default_welcome_message"],
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

    # Simple string settings — write directly if set
    _simple: dict[str, str | None] = {
        "tickets.channel_id": body.channel_id,
        "tickets.log_channel_id": body.log_channel_id,
        "tickets.close_message": body.close_message,
        "tickets.default_welcome_message": body.default_welcome_message,
    }
    for key, value in _simple.items():
        if value is not None:
            await config.set_guild_setting(guild_id, key, value)

    # Transformed settings
    if body.staff_roles is not None:
        await config.set_guild_setting(
            guild_id, "tickets.staff_roles", json.dumps([int(r) for r in body.staff_roles])
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
    channel_id: str | None = Query(None, description="Deploy to a specific channel"),
    current_user: UserProfile = Depends(require_discord_manager()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> dict:
    """Ask the bot to deploy (or refresh) ticket panels.

    If ``channel_id`` is provided, deploy to that specific channel only.
    Otherwise, deploy to all channels that have categories assigned.
    """
    guild_id = ensure_active_guild(current_user)

    try:
        result = await internal_api.deploy_ticket_panel(
            guild_id, channel_id=channel_id
        )
        return {
            "success": True,
            "message_id": result.get("message_id"),
            "panels": result.get("panels"),
        }
    except Exception as exc:
        logger.exception(
            "Failed to deploy ticket panel for guild %s", guild_id, exc_info=exc
        )
        raise translate_internal_api_error(
            exc,
            "Could not reach the bot to deploy the panel.",
        ) from exc
