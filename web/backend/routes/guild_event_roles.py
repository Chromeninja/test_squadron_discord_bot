"""Coordinator-only event role and signup-settings management routes.

All routes require event_coordinator or higher (bot owners always pass). Each
action verifies the event belongs to the guild before mutating role slots or
event-level signup settings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.dependencies import require_event_coordinator
from core.event_signup_service import (
    EventSignupService,
    SignupError,
    get_event_signup_service,
)
from core.schemas import (
    EventRoleCreateRequest,
    EventRoleSchema,
    EventRoleUpdateRequest,
    EventSettingsUpdateRequest,
    ScheduledEventResponse,
    UserProfile,
)
from core.validation import ensure_guild_match
from fastapi import APIRouter, Depends, HTTPException

from backend.db.repository.event_roles import EventRoleRepository
from backend.db.repository.events import EventRepository

if TYPE_CHECKING:
    from backend.db.repository.types import EventRoleRecord

router = APIRouter(prefix="/api/guilds", tags=["guild-event-roles"])
logger = logging.getLogger(__name__)


def _role_to_schema(role: EventRoleRecord, signup_count: int = 0) -> EventRoleSchema:
    """Convert a repository role dict into an EventRoleSchema."""
    return EventRoleSchema(
        id=role["id"],
        event_id=role["event_id"],
        name=role["name"],
        emoji=role["emoji"],
        description=role["description"],
        capacity=role["capacity"],
        sort_order=role["sort_order"],
        locked=role["locked"],
        signup_count=signup_count,
    )


async def _ensure_event_in_guild(
    service: EventSignupService, guild_id: int, event_id: int
) -> None:
    """Raise 404 if the event does not belong to the guild (coordinator view)."""
    try:
        await service.load_event(guild_id, event_id, is_coordinator=True)
    except SignupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/{guild_id}/events/{event_id}/roles",
    response_model=EventRoleSchema,
    status_code=201,
)
async def create_event_role(
    guild_id: int,
    event_id: int,
    payload: EventRoleCreateRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    roles: EventRoleRepository = Depends(EventRoleRepository),
):
    """Coordinator: create a new role slot for an event."""
    ensure_guild_match(guild_id, current_user)
    await _ensure_event_in_guild(service, guild_id, event_id)
    role = await roles.create_role(
        guild_id,
        event_id,
        payload.model_dump(),
        created_by_user_id=current_user.user_id,
    )
    await service.refresh_event_summary(guild_id, event_id)
    return _role_to_schema(role)


@router.patch(
    "/{guild_id}/events/{event_id}/roles/{role_id}",
    response_model=EventRoleSchema,
)
async def update_event_role(
    guild_id: int,
    event_id: int,
    role_id: int,
    payload: EventRoleUpdateRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    roles: EventRoleRepository = Depends(EventRoleRepository),
):
    """Coordinator: update a role slot (name, emoji, capacity, lock, order, ...)."""
    ensure_guild_match(guild_id, current_user)
    await _ensure_event_in_guild(service, guild_id, event_id)
    existing = await roles.get_role(guild_id, role_id)
    if existing is None or existing["event_id"] != event_id:
        raise HTTPException(status_code=404, detail="Role not found for this event")
    updated = await roles.update_role(
        guild_id,
        role_id,
        payload.model_dump(exclude_unset=True),
        updated_by_user_id=current_user.user_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Role not found")
    await service.refresh_event_summary(guild_id, event_id)
    return _role_to_schema(updated)


@router.delete("/{guild_id}/events/{event_id}/roles/{role_id}")
async def delete_event_role(
    guild_id: int,
    event_id: int,
    role_id: int,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    roles: EventRoleRepository = Depends(EventRoleRepository),
):
    """Coordinator: delete a role slot (cascades to its role signups)."""
    ensure_guild_match(guild_id, current_user)
    await _ensure_event_in_guild(service, guild_id, event_id)
    existing = await roles.get_role(guild_id, role_id)
    if existing is None or existing["event_id"] != event_id:
        raise HTTPException(status_code=404, detail="Role not found for this event")
    await roles.delete_role(guild_id, role_id)
    await service.refresh_event_summary(guild_id, event_id)
    return {"success": True}


@router.patch(
    "/{guild_id}/events/{event_id}/settings",
    response_model=ScheduledEventResponse,
)
async def update_event_settings(
    guild_id: int,
    event_id: int,
    payload: EventSettingsUpdateRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    events: EventRepository = Depends(EventRepository),
):
    """Coordinator: update event-level signup settings (enable/close/multiple)."""
    ensure_guild_match(guild_id, current_user)
    await _ensure_event_in_guild(service, guild_id, event_id)
    updated = await events.update_settings(
        guild_id,
        event_id,
        payload.model_dump(exclude_unset=True),
        updated_by_user_id=current_user.user_id,
        updated_by_name=current_user.username,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # Reuse the existing summary coercion from the scheduled-events route.
    from .guild_events import _coerce_scheduled_event_summary

    return ScheduledEventResponse(event=_coerce_scheduled_event_summary(updated))
