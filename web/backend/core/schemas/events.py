"""Scheduled event and synchronization schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ScheduledEventSummary(BaseModel):
    """Normalized Discord scheduled event metadata."""

    id: str
    name: str
    description: str | None = None
    scheduled_start_time: str | None = None
    scheduled_end_time: str | None = None
    status: str
    entity_type: str
    channel_id: str | None = None
    channel_name: str | None = None
    location: str | None = None
    user_count: int = 0
    creator_id: str | None = None
    creator_name: str | None = None
    image_url: str | None = None
    source_of_truth: str = "db"
    discord_event_id: str | None = None
    announcement_message_id: str | None = None
    signup_message_id: str | None = None
    sync_status: str = "pending"
    sync_error: str | None = None
    last_synced_at: int | None = None
    recurrence_rule: str | None = None


class ScheduledEventsResponse(BaseModel):
    """Response for /api/guilds/{guild_id}/events/scheduled."""

    success: bool = True
    events: list[ScheduledEventSummary]


class ScheduledEventCreateRequest(BaseModel):
    """Create request for a Discord scheduled event."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    announcement_message: str | None = Field(default=None, max_length=2000)
    scheduled_start_time: str
    scheduled_end_time: str | None = None
    entity_type: Literal["voice"]
    channel_id: str | None = None
    location: str | None = Field(default=None, max_length=100)
    announcement_channel_id: str | None = None
    signup_role_ids: list[str] = Field(default_factory=list)


class ScheduledEventUpdateRequest(ScheduledEventCreateRequest):
    """Update request for a Discord scheduled event."""


class ScheduledEventResponse(BaseModel):
    """Single scheduled event response wrapper."""

    success: bool = True
    event: ScheduledEventSummary


class EventSyncRequest(BaseModel):
    """Manual event synchronization request."""

    direction: Literal["push", "pull", "reconcile"] = "reconcile"
    event_id: str | None = None


class EventSyncResponse(BaseModel):
    """Manual event synchronization response."""

    success: bool = True
    processed: int = 0
    updated: int = 0
    direction: Literal["push", "pull", "reconcile"]
    events: list[ScheduledEventSummary] = Field(default_factory=list)
