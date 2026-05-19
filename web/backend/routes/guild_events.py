"""Discord scheduled event management routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_event_coordinator,
    require_fresh_guild_access,
    translate_internal_api_error,
)
from core.event_service import EventService
from core.schemas import (
    EventSyncRequest,
    EventSyncResponse,
    ScheduledEventCreateRequest,
    ScheduledEventResponse,
    ScheduledEventsResponse,
    ScheduledEventSummary,
    ScheduledEventUpdateRequest,
    UserProfile,
)
from core.validation import (
    ensure_guild_match,
    parse_snowflake_id_optional,
    safe_int,
)
from fastapi import APIRouter, Depends, HTTPException

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/guilds", tags=["guild-events"])
logger = logging.getLogger(__name__)


def _coerce_scheduled_event_summary(
    event_data: dict[str, object | None],
) -> ScheduledEventSummary:
    """Coerce event payload values into strict ScheduledEventSummary types."""
    last_synced_at_raw = event_data.get("last_synced_at")
    last_synced_at = (
        int(last_synced_at_raw)
        if isinstance(last_synced_at_raw, (int, str))
        and str(last_synced_at_raw).strip()
        else None
    )
    user_count_raw = event_data.get("user_count")
    user_count = (
        int(user_count_raw)
        if isinstance(user_count_raw, (int, str)) and str(user_count_raw).strip()
        else 0
    )

    return ScheduledEventSummary(
        id=str(event_data.get("id") or ""),
        name=str(event_data.get("name") or ""),
        description=(
            str(event_data["description"])
            if isinstance(event_data.get("description"), str)
            else None
        ),
        scheduled_start_time=(
            str(event_data["scheduled_start_time"])
            if isinstance(event_data.get("scheduled_start_time"), str)
            else None
        ),
        scheduled_end_time=(
            str(event_data["scheduled_end_time"])
            if isinstance(event_data.get("scheduled_end_time"), str)
            else None
        ),
        status=str(event_data.get("status") or "scheduled"),
        entity_type=str(event_data.get("entity_type") or "voice"),
        channel_id=(
            str(event_data["channel_id"])
            if isinstance(event_data.get("channel_id"), str)
            else None
        ),
        channel_name=(
            str(event_data["channel_name"])
            if isinstance(event_data.get("channel_name"), str)
            else None
        ),
        location=(
            str(event_data["location"])
            if isinstance(event_data.get("location"), str)
            else None
        ),
        user_count=user_count,
        creator_id=(
            str(event_data["creator_id"])
            if isinstance(event_data.get("creator_id"), str)
            else None
        ),
        creator_name=(
            str(event_data["creator_name"])
            if isinstance(event_data.get("creator_name"), str)
            else None
        ),
        image_url=(
            str(event_data["image_url"])
            if isinstance(event_data.get("image_url"), str)
            else None
        ),
        source_of_truth=str(event_data.get("source_of_truth") or "db"),
        discord_event_id=(
            str(event_data["discord_event_id"])
            if isinstance(event_data.get("discord_event_id"), str)
            else None
        ),
        announcement_message_id=(
            str(event_data["announcement_message_id"])
            if isinstance(event_data.get("announcement_message_id"), str)
            else None
        ),
        signup_message_id=(
            str(event_data["signup_message_id"])
            if isinstance(event_data.get("signup_message_id"), str)
            else None
        ),
        sync_status=str(event_data.get("sync_status") or "pending"),
        sync_error=(
            str(event_data["sync_error"])
            if isinstance(event_data.get("sync_error"), str)
            else None
        ),
        last_synced_at=last_synced_at,
        recurrence_rule=(
            str(event_data["recurrence_rule"])
            if isinstance(event_data.get("recurrence_rule"), str)
            else None
        ),
    )


@router.get(
    "/{guild_id}/events/scheduled",
    response_model=ScheduledEventsResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_discord_scheduled_events(
    guild_id: int,
    current_user: UserProfile = Depends(require_event_coordinator()),
):
    """Return DB-backed scheduled events for a guild (DB is source of truth)."""
    ensure_guild_match(guild_id, current_user)
    events_payload = await EventService.list_events(guild_id)

    return ScheduledEventsResponse(
        events=[_coerce_scheduled_event_summary(event) for event in events_payload]
    )


@router.get(
    "/{guild_id}/events/scheduled/{event_id}",
    response_model=ScheduledEventResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_discord_scheduled_event(
    guild_id: int,
    event_id: int,
    current_user: UserProfile = Depends(require_event_coordinator()),
):
    """Return a single DB-backed scheduled event by local ID."""
    ensure_guild_match(guild_id, current_user)
    event_payload = await EventService.get_event(guild_id, event_id)
    if event_payload is None:
        raise HTTPException(status_code=404, detail="Scheduled event not found")

    return ScheduledEventResponse(event=_coerce_scheduled_event_summary(event_payload))


@router.post(
    "/{guild_id}/events/scheduled",
    response_model=ScheduledEventResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def create_discord_scheduled_event(
    guild_id: int,
    payload: ScheduledEventCreateRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Create a scheduled event (DB first), then project to Discord."""
    ensure_guild_match(guild_id, current_user)

    channel_id = parse_snowflake_id_optional(payload.channel_id)
    create_payload: dict[str, object | None] = {
        "name": payload.name,
        "description": payload.description,
        "announcement_message": payload.announcement_message,
        "scheduled_start_time": payload.scheduled_start_time,
        "scheduled_end_time": payload.scheduled_end_time,
        "entity_type": payload.entity_type,
        "channel_id": str(channel_id) if channel_id is not None else None,
        "location": payload.location,
        "announcement_channel_id": payload.announcement_channel_id,
        "signup_role_ids": payload.signup_role_ids,
        "created_by_name": current_user.username,
    }

    created_event = await EventService.create_event(
        guild_id=guild_id,
        payload=create_payload,
        created_by_user_id=current_user.user_id,
        created_by_name=current_user.username,
    )

    try:
        projected_event = await EventService.sync_db_event_to_discord(
            guild_id=guild_id,
            event=created_event,
            projection_client=internal_api,
        )
        return ScheduledEventResponse(
            event=_coerce_scheduled_event_summary(projected_event)
        )
    except Exception as exc:
        logger.warning(
            "Managed event %s created in DB but Discord projection failed: %s",
            created_event.get("id"),
            exc,
        )

    latest_event = await EventService.get_event(guild_id, int(str(created_event["id"])))
    if latest_event is None:
        raise HTTPException(status_code=500, detail="Created event could not be loaded")
    return ScheduledEventResponse(event=_coerce_scheduled_event_summary(latest_event))


@router.put(
    "/{guild_id}/events/scheduled/{event_id}",
    response_model=ScheduledEventResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def update_discord_scheduled_event(
    guild_id: int,
    event_id: int,
    payload: ScheduledEventUpdateRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Update a scheduled event (DB first), then project to Discord."""
    ensure_guild_match(guild_id, current_user)

    channel_id = parse_snowflake_id_optional(payload.channel_id)
    update_payload: dict[str, object | None] = {
        "name": payload.name,
        "description": payload.description,
        "announcement_message": payload.announcement_message,
        "scheduled_start_time": payload.scheduled_start_time,
        "scheduled_end_time": payload.scheduled_end_time,
        "entity_type": payload.entity_type,
        "channel_id": str(channel_id) if channel_id is not None else None,
        "location": payload.location,
        "announcement_channel_id": payload.announcement_channel_id,
        "signup_role_ids": payload.signup_role_ids,
    }

    updated_event = await EventService.update_event(
        guild_id=guild_id,
        event_id=event_id,
        payload=update_payload,
        updated_by_user_id=current_user.user_id,
        updated_by_name=current_user.username,
    )
    if updated_event is None:
        raise HTTPException(status_code=404, detail="Scheduled event not found")

    try:
        projected_event = await EventService.sync_db_event_to_discord(
            guild_id=guild_id,
            event=updated_event,
            projection_client=internal_api,
        )
        return ScheduledEventResponse(
            event=_coerce_scheduled_event_summary(projected_event)
        )
    except Exception as exc:
        logger.warning(
            "Managed event %s updated in DB but Discord projection failed: %s",
            updated_event.get("id"),
            exc,
        )

    latest_event = await EventService.get_event(guild_id, event_id)
    if latest_event is None:
        raise HTTPException(status_code=404, detail="Scheduled event not found")
    return ScheduledEventResponse(event=_coerce_scheduled_event_summary(latest_event))


@router.post(
    "/{guild_id}/events/scheduled/sync",
    response_model=EventSyncResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def sync_discord_scheduled_events(
    guild_id: int,
    payload: EventSyncRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Run manual DB/Discord synchronization for managed events."""
    ensure_guild_match(guild_id, current_user)

    target_event_id = (
        int(payload.event_id)
        if isinstance(payload.event_id, str) and payload.event_id.strip()
        else None
    )

    try:
        result, events = await EventService.manual_sync(
            guild_id=guild_id,
            direction=payload.direction,
            projection_client=internal_api,
            event_id=target_event_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise translate_internal_api_error(
            exc,
            "Failed to synchronize scheduled events",
        ) from exc

    return EventSyncResponse(
        direction=payload.direction,
        processed=result.processed,
        updated=result.updated,
        events=[_coerce_scheduled_event_summary(event) for event in events],
    )
