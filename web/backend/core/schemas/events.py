"""Scheduled event and synchronization schemas."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ScheduledEventRecurrenceNWeekday(BaseModel):
    """N-th weekday recurrence helper."""

    n: int = Field(ge=1, le=5)
    day: Literal[0, 1, 2, 3, 4, 5, 6]


class ScheduledEventRecurrenceRule(BaseModel):
    """Discord-compatible recurrence rule payload for scheduled events."""

    start: str
    frequency: Literal[0, 1, 2, 3]
    interval: int = Field(default=1, ge=1)
    by_weekday: list[Literal[0, 1, 2, 3, 4, 5, 6]] | None = None
    by_n_weekday: list[ScheduledEventRecurrenceNWeekday] | None = None
    by_month: list[int] | None = Field(default=None)
    by_month_day: list[int] | None = Field(default=None)


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
    recurrence_rule_payload: ScheduledEventRecurrenceRule | None = None
    # Web signup state (DB-backed; separate from Discord's native user_count)
    signups_enabled: bool = True
    signups_closed: bool = False
    allow_multiple_roles: bool = False
    signup_channel_id: str | None = None
    web_signup_count: int = 0
    current_user_signed_up: bool = False
    current_user_signup_id: int | None = None


class EventRoleSchema(BaseModel):
    """A per-event role slot with its current signup count."""

    id: int
    event_id: int
    name: str
    emoji: str | None = None
    description: str | None = None
    capacity: int | None = None
    sort_order: int = 0
    locked: bool = False
    signup_count: int = 0
    current_user_signed_up: bool = False


class EventRolesResponse(BaseModel):
    """Response listing the roles for an event plus current-user state."""

    success: bool = True
    roles: list[EventRoleSchema] = Field(default_factory=list)
    allow_multiple_roles: bool = False
    signups_enabled: bool = True
    signups_closed: bool = False


class EventRoleCreateRequest(BaseModel):
    """Coordinator request to create an event role slot."""

    name: str = Field(min_length=1, max_length=40)
    emoji: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=280)
    capacity: int | None = Field(default=None, ge=1)
    sort_order: int = 0
    locked: bool = False


class EventRoleUpdateRequest(BaseModel):
    """Coordinator request to update an event role slot (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=40)
    emoji: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=280)
    capacity: int | None = Field(default=None, ge=1)
    sort_order: int | None = None
    locked: bool | None = None


class EventRoleSignupRequest(BaseModel):
    """Request to sign up for (or be assigned to) a specific event role."""

    role_id: int


class EventSettingsUpdateRequest(BaseModel):
    """Coordinator request to update event-level signup settings."""

    signups_enabled: bool | None = None
    signups_closed: bool | None = None
    allow_multiple_roles: bool | None = None
    signup_channel_id: str | None = None


class EventRosterUser(BaseModel):
    """A user appearing in the coordinator roster."""

    user_id: str
    display_name: str | None = None
    created_at: int | None = None


class EventRosterRole(BaseModel):
    """Roster breakdown for a single role."""

    role_id: int
    name: str
    emoji: str | None = None
    capacity: int | None = None
    locked: bool = False
    users: list[EventRosterUser] = Field(default_factory=list)


class EventRosterResponse(BaseModel):
    """Full coordinator roster: web signups separated from Discord RSVP."""

    success: bool = True
    event_id: int
    total_web_signups: int = 0
    # Web-interested users who have not selected any role.
    no_role_users: list[EventRosterUser] = Field(default_factory=list)
    roles: list[EventRosterRole] = Field(default_factory=list)
    # Discord-native RSVP/interest count, kept separate from web signups.
    discord_user_count: int = 0


class EventMessageRequest(BaseModel):
    """Coordinator request to send a message to a signup segment."""

    channel_id: str
    message: str = Field(min_length=1, max_length=2000)
    target: Literal["all", "no_role", "role", "all_roles"] = "all"
    role_id: int | None = None

    @model_validator(mode="after")
    def validate_role_target(self) -> "EventMessageRequest":
        """Require role_id when targeting a single role."""
        if self.target == "role" and self.role_id is None:
            raise ValueError("role_id is required when target is 'role'")
        return self


class EventMessageResponse(BaseModel):
    """Result of sending a coordinator message."""

    success: bool = True
    recipients: int = 0


class EventSignupResponse(BaseModel):
    """Whole-event interest signup state response."""

    success: bool = True
    event_id: int
    signed_up: bool = False
    web_signup_count: int = 0


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
    entity_type: Literal["stage_instance", "voice", "external"]
    channel_id: str | None = None
    location: str | None = Field(default=None, max_length=100)
    announcement_channel_id: str | None = None
    recurrence_rule: ScheduledEventRecurrenceRule | None = None
    image_data: str | None = None

    @model_validator(mode="after")
    def validate_location_fields(self) -> "ScheduledEventCreateRequest":
        """Validate mode-specific Discord location fields."""
        if self.entity_type == "external":
            if not self.location or not self.location.strip():
                raise ValueError("External events require a location")
            if self.channel_id is not None:
                raise ValueError("External events cannot include a channel_id")
            return self

        if not self.channel_id:
            raise ValueError("Stage and voice events require a channel_id")
        return self


class ScheduledEventUpdateRequest(ScheduledEventCreateRequest):
    """Update request for a Discord scheduled event."""


class ScheduledEventResponse(BaseModel):
    """Single scheduled event response wrapper."""

    success: bool = True
    event: ScheduledEventSummary


class ScheduledEventDeleteResponse(BaseModel):
    """Delete scheduled event response wrapper."""

    success: bool = True


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
