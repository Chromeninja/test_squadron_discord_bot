"""Typed records returned by event repositories.

These contracts describe normalized values after a database row has crossed
the repository boundary.  Callers should not need to coerce scalar fields or
know that SQLite stores booleans as integers.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class EventRoleRecord(TypedDict):
    """A normalized row from ``event_roles``."""

    id: int
    guild_id: int
    event_id: int
    name: str
    emoji: str | None
    description: str | None
    capacity: int | None
    sort_order: int
    locked: bool
    created_at: int
    updated_at: int


class EventSignupRecord(TypedDict):
    """A normalized row from ``event_signups``."""

    id: int
    guild_id: int
    event_id: int
    user_id: str
    created_at: int
    updated_at: int


class EventRoleSignupRecord(TypedDict):
    """A normalized row from ``event_role_signups``."""

    id: int
    guild_id: int
    event_id: int
    role_id: int
    user_id: str
    created_at: int
    updated_at: int


class ManagedEventRecord(TypedDict):
    """A normalized managed event returned by the database layer."""

    id: str
    name: str
    description: str | None
    announcement_message: str | None
    scheduled_start_time: str | None
    scheduled_end_time: str | None
    status: str
    entity_type: str
    channel_id: str | None
    channel_name: str | None
    location: str | None
    user_count: int
    creator_id: str | None
    creator_name: str | None
    image_url: str | None
    source_of_truth: str
    discord_event_id: str | None
    announcement_message_id: str | None
    signup_message_id: str | None
    sync_status: str
    sync_error: str | None
    last_synced_at: int | None
    announcement_channel_id: str | None
    revision: int
    recurrence_rule: str | None
    recurrence_rule_payload: dict[str, object] | None
    signups_enabled: bool
    signups_closed: bool
    allow_multiple_roles: bool
    signup_channel_id: str | None

    # Request-specific enrichments attached by the signup service.
    web_signup_count: NotRequired[int]
    current_user_signed_up: NotRequired[bool]
    current_user_signup_id: NotRequired[int | None]
    image_data: NotRequired[object | None]
