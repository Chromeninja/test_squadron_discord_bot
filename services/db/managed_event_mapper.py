"""Mapping helpers for managed event rows and payload fields."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

    from backend.db.repository.types import ManagedEventRecord


def _row_get(
    row: aiosqlite.Row, key: str, default: object | None = None
) -> object | None:
    """Safely read a column from a Row/dict, tolerating legacy rows.

    aiosqlite.Row raises IndexError for unknown columns and dict raises
    KeyError; both are treated as "column absent" so callers degrade to the
    provided default (used for the signup setting columns on legacy rows).
    """
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _optional_str(value: object | None) -> str | None:
    """Normalize an optional SQLite text value."""
    return str(value) if value is not None else None


def _required_str(value: object | None) -> str:
    """Normalize a required SQLite text value."""
    return str(value) if value is not None else ""


def managed_event_row_to_dict(row: aiosqlite.Row) -> ManagedEventRecord:
    """Convert a managed event row into API-facing event payload fields."""
    recurrence_rule_payload_raw = row["recurrence_rule_payload"]
    recurrence_rule_payload: dict[str, object] | None = None
    if isinstance(recurrence_rule_payload_raw, str) and recurrence_rule_payload_raw:
        try:
            parsed_payload = json.loads(recurrence_rule_payload_raw)
        except Exception:
            parsed_payload = None
        if isinstance(parsed_payload, dict) and all(
            isinstance(key, str) for key in parsed_payload
        ):
            recurrence_rule_payload = {
                str(key): value for key, value in parsed_payload.items()
            }

    return {
        "id": str(row["id"]),
        "name": _required_str(row["name"]),
        "description": _optional_str(row["description"]),
        "announcement_message": _optional_str(row["announcement_message"]),
        "scheduled_start_time": _optional_str(row["scheduled_start_time"]),
        "scheduled_end_time": _optional_str(row["scheduled_end_time"]),
        "status": _required_str(row["status"]),
        "entity_type": _required_str(row["entity_type"]),
        "channel_id": _optional_str(row["channel_id"]),
        "channel_name": _optional_str(row["channel_name"]),
        "location": _optional_str(row["location"]),
        "user_count": int(row["user_count_current"]),
        "creator_id": _optional_str(row["created_by_user_id"]),
        "creator_name": _optional_str(row["created_by_name"]),
        "image_url": _optional_str(row["image_url"]),
        "source_of_truth": "db",
        "discord_event_id": _optional_str(row["discord_event_id"]),
        "announcement_message_id": _optional_str(row["announcement_message_id"]),
        "signup_message_id": _optional_str(row["signup_message_id"]),
        "sync_status": _required_str(row["sync_status"]),
        "sync_error": _optional_str(row["sync_error"]),
        "last_synced_at": (
            int(row["last_synced_at"]) if row["last_synced_at"] is not None else None
        ),
        "announcement_channel_id": _optional_str(row["announcement_channel_id"]),
        "revision": int(row["revision"]),
        "recurrence_rule": _optional_str(row["recurrence_rule"]),
        "recurrence_rule_payload": recurrence_rule_payload,
        # Event-level web signup settings (defensive: legacy rows may predate
        # these columns until the migration runs).
        "signups_enabled": bool(_row_get(row, "signups_enabled", 1)),
        "signups_closed": bool(_row_get(row, "signups_closed", 0)),
        "allow_multiple_roles": bool(_row_get(row, "allow_multiple_roles", 0)),
        "signup_channel_id": _optional_str(
            _row_get(row, "signup_channel_id", None)
        ),
    }
