"""Mapping helpers for managed event rows and payload fields."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite


def _row_get(row: aiosqlite.Row, key: str, default: object | None = None) -> object | None:
    """Safely read a column from a Row/dict, tolerating legacy rows.

    aiosqlite.Row raises IndexError for unknown columns and dict raises
    KeyError; both are treated as "column absent" so callers degrade to the
    provided default (used for the signup setting columns on legacy rows).
    """
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def managed_event_row_to_dict(row: aiosqlite.Row) -> dict[str, object | None]:
    """Convert a managed event row into API-facing event payload fields."""
    recurrence_rule_payload_raw = row["recurrence_rule_payload"]
    recurrence_rule_payload: dict[str, object] | None = None
    if isinstance(recurrence_rule_payload_raw, str) and recurrence_rule_payload_raw:
        try:
            parsed_payload = json.loads(recurrence_rule_payload_raw)
        except Exception:
            parsed_payload = None
        if isinstance(parsed_payload, dict):
            recurrence_rule_payload = parsed_payload

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
        "channel_name": row["channel_name"],
        "location": row["location"],
        "user_count": int(row["user_count_current"]),
        "creator_id": row["created_by_user_id"],
        "creator_name": row["created_by_name"],
        "image_url": row["image_url"],
        "source_of_truth": "db",
        "discord_event_id": row["discord_event_id"],
        "announcement_message_id": row["announcement_message_id"],
        "signup_message_id": row["signup_message_id"],
        "sync_status": row["sync_status"],
        "sync_error": row["sync_error"],
        "last_synced_at": row["last_synced_at"],
        "announcement_channel_id": row["announcement_channel_id"],
        "revision": int(row["revision"]),
        "recurrence_rule": row["recurrence_rule"],
        "recurrence_rule_payload": recurrence_rule_payload,
        # Event-level web signup settings (defensive: legacy rows may predate
        # these columns until the migration runs).
        "signups_enabled": bool(_row_get(row, "signups_enabled", 1)),
        "signups_closed": bool(_row_get(row, "signups_closed", 0)),
        "allow_multiple_roles": bool(_row_get(row, "allow_multiple_roles", 0)),
        "signup_channel_id": _row_get(row, "signup_channel_id", None),
    }
