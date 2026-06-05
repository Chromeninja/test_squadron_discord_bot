"""
Ticket management API endpoints.

Provides CRUD for ticket categories, ticket listing/stats, and
guild-level ticket settings — all scoped to the active guild.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from core.dependencies import (
    InternalAPIClient,
    get_config_service,
    get_internal_api_client,
    get_ticket_repository,
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

from helpers.role_ids import normalize_role_id_list
from utils.logging import get_logger
from web.backend.routes._ticket_helpers import require_guild_category
from web.backend.routes.users import _get_member_with_cache

if TYPE_CHECKING:
    from backend.db.repository.tickets import TicketRepository
    from services.config_service import ConfigService

logger = get_logger(__name__)

router = APIRouter()


async def _resolve_ticket_creators(
    internal_api: InternalAPIClient,
    guild_id: int,
    user_ids: set[int],
) -> dict[int, dict[str, str | None]]:
    """Resolve creator identity data for a set of Discord user IDs.

    Uses the shared member cache lookup from users routes so tickets follow
    the same resolution behavior as other dashboard pages.
    """
    if not user_ids:
        return {}

    async def _resolve_one(user_id: int) -> tuple[int, dict[str, str | None]]:
        try:
            member_data = await _get_member_with_cache(internal_api, guild_id, user_id)
        except Exception as exc:
            logger.debug(
                "Failed to resolve ticket creator for guild %s user %s",
                guild_id,
                user_id,
                exc_info=exc,
            )
            return (
                user_id,
                {
                    "creator_username": None,
                    "creator_global_name": None,
                    "creator_discriminator": None,
                    "creator_avatar_url": None,
                },
            )

        username = member_data.get("username")
        global_name = member_data.get("global_name")
        discriminator = member_data.get("discriminator")
        avatar_url = member_data.get("avatar_url")
        return (
            user_id,
            {
                "creator_username": str(username) if username else None,
                "creator_global_name": str(global_name) if global_name else None,
                "creator_discriminator": (
                    str(discriminator) if discriminator else None
                ),
                "creator_avatar_url": str(avatar_url) if avatar_url else None,
            },
        )

    resolved_pairs = await asyncio.gather(
        *(_resolve_one(user_id) for user_id in user_ids)
    )
    return dict(resolved_pairs)


def _parse_role_id_list(field_name: str, raw_role_ids: list[str]) -> list[int]:
    """Parse role ID list from API payload and raise 422 on invalid values."""
    try:
        return normalize_role_id_list(raw_role_ids, strict=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role ID in {field_name}",
        ) from exc


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
                str(role_id) for role_id in c.get("prerequisite_role_ids_all", [])
            ],
            prerequisite_role_ids_any=[
                str(role_id) for role_id in c.get("prerequisite_role_ids_any", [])
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
    repo: TicketRepository = Depends(get_ticket_repository),
) -> TicketCategoryListResponse:
    """List all ticket categories for the active guild."""
    guild_id = ensure_active_guild(current_user)
    cats = await repo.get_categories(guild_id)
    return _build_category_list(cats)


@router.post("/categories", response_model=TicketCategoryListResponse, status_code=201)
async def create_category(
    body: TicketCategoryCreate,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> TicketCategoryListResponse:
    """Create a new ticket category."""
    guild_id = ensure_active_guild(current_user)
    # Ensure the body guild_id matches the active guild
    if str(guild_id) != body.guild_id:
        raise HTTPException(status_code=403, detail="Guild mismatch")
    cat_id = await repo.create_category(
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
    cats = await repo.get_categories(guild_id)
    return _build_category_list(cats)


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: TicketCategoryUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict:
    """Update a ticket category."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(repo, category_id, guild_id)

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

    updated = await repo.update_category(category_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Category not found")

    return {"success": True}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict:
    """Delete a ticket category."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(repo, category_id, guild_id)

    deleted = await repo.delete_category(category_id)
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
            public_button_text=c.get("public_button_text", "Create Public Ticket"),
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
    repo: TicketRepository, guild_id: int, channel_id: int
) -> dict:
    """Verify a channel config exists and belongs to the given guild.

    Raises ``HTTPException(404)`` on mismatch.
    """
    cfg = await repo.get_channel_config(guild_id, channel_id)
    if cfg is None or cfg["guild_id"] != guild_id:
        raise HTTPException(status_code=404, detail="Channel config not found")
    return cfg


@router.get("/channels", response_model=TicketChannelConfigListResponse)
async def list_channel_configs(
    current_user: UserProfile = Depends(require_staff()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> TicketChannelConfigListResponse:
    """List all ticket channel configs for the active guild."""
    guild_id = ensure_active_guild(current_user)
    configs = await repo.get_channel_configs(guild_id)
    return _build_channel_config_list(configs)


@router.post(
    "/channels", response_model=TicketChannelConfigListResponse, status_code=201
)
async def create_channel_config(
    body: TicketChannelConfigCreate,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> TicketChannelConfigListResponse:
    """Create a new ticket channel config."""
    guild_id = ensure_active_guild(current_user)
    # Ensure the body guild_id matches the active guild
    if str(guild_id) != body.guild_id:
        raise HTTPException(status_code=403, detail="Guild mismatch")

    # Check if config already exists
    existing = await repo.get_channel_config(guild_id, int(body.channel_id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Channel config already exists")

    config_id = await repo.create_channel_config(
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
        raise HTTPException(status_code=500, detail="Failed to create channel config")

    # Return updated list
    configs = await repo.get_channel_configs(guild_id)
    return _build_channel_config_list(configs)


@router.put("/channels/{channel_id}")
async def update_channel_config(
    channel_id: str,
    body: TicketChannelConfigUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict:
    """Update a ticket channel config."""
    guild_id = ensure_active_guild(current_user)
    channel_id_int = int(channel_id)
    await _require_guild_channel_config(repo, guild_id, channel_id_int)

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
        updated = await repo.update_channel_config(guild_id, channel_id_int, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Channel config not found")

    return {"success": True}


@router.delete("/channels/{channel_id}")
async def delete_channel_config(
    channel_id: str,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> dict:
    """Delete a ticket channel config.

    AI Notes:
        This does NOT delete categories assigned to the channel.
        They will become unassigned (channel_id = 0).
    """
    guild_id = ensure_active_guild(current_user)
    channel_id_int = int(channel_id)
    await _require_guild_channel_config(repo, guild_id, channel_id_int)

    deleted = await repo.delete_channel_config(guild_id, channel_id_int)
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
    repo: TicketRepository = Depends(get_ticket_repository),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> TicketListResponse:
    """List tickets for the active guild with optional status filter."""
    guild_id = ensure_active_guild(current_user)

    def _parse_ticket_user_id(raw_user_id: Any) -> int | None:
        if raw_user_id is None:
            return None
        try:
            return int(raw_user_id)
        except (TypeError, ValueError):
            return None

    offset = (page - 1) * page_size
    tickets = await repo.get_tickets(
        guild_id, status=status, limit=page_size, offset=offset
    )
    total = await repo.get_ticket_count(guild_id, status=status)

    creator_user_ids: set[int] = {
        parsed_user_id
        for ticket in tickets
        if (parsed_user_id := _parse_ticket_user_id(ticket.get("user_id"))) is not None
    }
    creator_map = await _resolve_ticket_creators(
        internal_api,
        guild_id,
        creator_user_ids,
    )

    items: list[TicketInfo] = []
    for t in tickets:
        creator_user_id = _parse_ticket_user_id(t.get("user_id"))
        creator_data = (
            creator_map.get(creator_user_id, {}) if creator_user_id is not None else {}
        )

        raw_cat_id = t.get("category_id")
        items.append(
            TicketInfo(
                id=int(t["id"]),  # type: ignore[arg-type]
                guild_id=str(t["guild_id"]),
                channel_id=str(t["channel_id"]),
                thread_id=str(t["thread_id"]),
                user_id=str(t["user_id"]),
                creator_username=creator_data.get("creator_username"),
                creator_global_name=creator_data.get("creator_global_name"),
                creator_discriminator=creator_data.get("creator_discriminator"),
                creator_avatar_url=creator_data.get("creator_avatar_url"),
                category_id=int(raw_cat_id) if raw_cat_id is not None else None,  # type: ignore[arg-type]
                status=str(t["status"]),
                closed_by=str(t["closed_by"]) if t.get("closed_by") else None,
                created_at=int(t.get("created_at") or 0),  # type: ignore[arg-type]
                closed_at=int(t["closed_at"])
                if t.get("closed_at") is not None
                else None,  # type: ignore[arg-type]
                claimed_by=str(t["claimed_by"]) if t.get("claimed_by") else None,
                claimed_at=int(t["claimed_at"])
                if t.get("claimed_at") is not None
                else None,  # type: ignore[arg-type]
                close_reason=str(t["close_reason"])
                if t.get("close_reason") is not None
                else None,
                initial_description=str(t["initial_description"])
                if t.get("initial_description") is not None
                else None,
                reopened_at=int(t["reopened_at"])
                if t.get("reopened_at") is not None
                else None,  # type: ignore[arg-type]
                reopened_by=str(t["reopened_by"]) if t.get("reopened_by") else None,
            )
        )
    return TicketListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=TicketStatsResponse)
async def ticket_stats(
    current_user: UserProfile = Depends(require_staff()),
    repo: TicketRepository = Depends(get_ticket_repository),
) -> TicketStatsResponse:
    """Get ticket statistics for the active guild."""
    guild_id = ensure_active_guild(current_user)
    data = await repo.get_ticket_stats(guild_id)
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
        "tickets.channel_id",
        "tickets.panel_message_id",
        "tickets.log_channel_id",
        "tickets.close_message",
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

    raw_roles = await config.get_guild_setting(
        guild_id, "tickets.staff_roles", default="[]"
    )
    try:
        parsed = raw_roles
        for _ in range(2):
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
                continue
            break
        staff_roles: list[int] = [int(r) for r in (parsed or [])]
    except (json.JSONDecodeError, TypeError, ValueError):
        staff_roles = []

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
            guild_id,
            "tickets.staff_roles",
            json.dumps([int(r) for r in body.staff_roles]),
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
        result = await internal_api.deploy_ticket_panel(guild_id, channel_id=channel_id)
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
