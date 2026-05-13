"""Mapping helpers for managed event rows and payload fields."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite


def decode_signup_role_ids(raw_value: str | None) -> list[str]:
    """Decode persisted signup role IDs from JSON into a normalized list."""
    if not raw_value:
        return []

    try:
        decoded = json.loads(raw_value)
    except Exception:
        return []

    if not isinstance(decoded, list):
        return []

    normalized: list[str] = []
    for role_id in decoded:
        if isinstance(role_id, (str, int)):
            normalized.append(str(role_id))
    return normalized


def managed_event_row_to_dict(row: aiosqlite.Row) -> dict[str, object | None]:
    """Convert a managed event row into API-facing event payload fields."""
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "announcement_message": row["announcement_message"],
        "scheduled_start_time": row["scheduled_start_time"],
        "scheduled_end_time": row["scheduled_end_time"],
        "status": row["status"],
        "entity_type": row["entity_type"],
        "channel_id": row["channel_id"],
        "channel_name": None,
        "location": row["location"],
        "user_count": int(row["user_count_current"]),
        "creator_id": row["created_by_user_id"],
        "creator_name": row["created_by_name"],
        "image_url": None,
        "source_of_truth": "db",
        "discord_event_id": row["discord_event_id"],
        "announcement_message_id": row["announcement_message_id"],
        "signup_message_id": row["signup_message_id"],
        "sync_status": row["sync_status"],
        "sync_error": row["sync_error"],
        "last_synced_at": row["last_synced_at"],
        "announcement_channel_id": row["announcement_channel_id"],
        "signup_role_ids": decode_signup_role_ids(row["signup_role_ids"]),
        "revision": int(row["revision"]),
        "recurrence_rule": row["recurrence_rule"],
    }
