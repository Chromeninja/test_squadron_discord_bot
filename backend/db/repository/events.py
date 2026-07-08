"""EventRepository — thin wrapper around Database class for managed event queries.

This module extracts all event/managed_event DB query methods from
web/backend/core/event_service.py and services/db/managed_event_mapper.py
into a clean repository class that takes no direct aiosqlite connection —
it delegates to the existing Database class methods which handle their own
connections via the async context manager pattern.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from services.db.database import Database

# Event statuses that mean the event is over and should never be shown to
# regular guild members in the active/upcoming/recurring view.
_TERMINAL_STATUSES = {"completed", "ended", "cancelled", "canceled"}
# Statuses that keep an event visible even if its start time has passed.
_EXPLICITLY_ACTIVE_STATUSES = {"active", "in_progress", "ongoing"}

# Short-TTL per-guild cache for the managed-events list. The event list is the
# hottest dashboard read (every user hits it on login) while events change
# rarely, so a few seconds of staleness is invisible to users but collapses DB
# load under high concurrency. Web-process writes invalidate immediately;
# bot-process writes (Discord sync) become visible within the TTL. The cache
# is per-process, which keeps it safe across multiple uvicorn workers.
_EVENTS_CACHE_TTL_SECONDS = 5.0
_events_cache: dict[int, tuple[float, list[dict[str, object | None]]]] = {}


def invalidate_events_cache(guild_id: int) -> None:
    """Drop the cached event list for a guild after any event write."""
    _events_cache.pop(guild_id, None)


async def _list_events_cached(guild_id: int) -> list[dict[str, object | None]]:
    """Return the guild's managed events, cached for a few seconds.

    Returns per-call dict copies because callers mutate the event payloads
    (signup state attachment) — the cached originals must stay pristine.
    """
    now = time.monotonic()
    cached = _events_cache.get(guild_id)
    if cached is not None and now - cached[0] < _EVENTS_CACHE_TTL_SECONDS:
        return [dict(event) for event in cached[1]]
    events = await Database.list_managed_events_by_guild(guild_id)
    _events_cache[guild_id] = (now, events)
    return [dict(event) for event in events]


def _parse_iso_to_ts(value: object) -> float | None:
    """Best-effort parse of an ISO 8601 datetime string to a unix timestamp."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def is_active_event(
    event: dict[str, object | None], *, now: float | None = None
) -> bool:
    """Return True when an event is active/upcoming/recurring (not past).

    This mirrors the frontend ``isPastEvent`` logic so backend enforcement and
    UX filtering stay consistent:
      - terminal statuses are always past
      - recurring events (recurrence_rule set) are always active
      - a one-off event whose end time has passed is past
      - a one-off event whose start time has passed is past unless its status is
        explicitly active

    This function is the single choke point for event visibility decisions.

    TODO(channel-visibility): a future pass can extend this to accept a user_id
    and hide events whose attached Discord channel the user cannot view (hidden
    or read-only channels). The guild_id and per-user request context are
    intentionally available at the call sites so this can be added without a
    schema change.
    """
    status = str(event.get("status") or "").lower()
    if status in _TERMINAL_STATUSES:
        return False

    if event.get("recurrence_rule"):
        return True

    current = now if now is not None else time.time()

    end_ts = _parse_iso_to_ts(event.get("scheduled_end_time"))
    if end_ts is not None and end_ts < current:
        return False

    start_ts = _parse_iso_to_ts(event.get("scheduled_start_time"))
    if (
        start_ts is not None
        and start_ts < current
        and status not in _EXPLICITLY_ACTIVE_STATUSES
    ):
        return False

    return True


class EventRepository:
    """Repository for managed_events table operations.

    Takes no database instance in __init__ because the underlying Database
    class manages its own connection pool via the get_connection() context manager.
    The guild_id parameter is required on every method to ensure all queries
    are properly scoped to a single guild.
    """

    async def get_managed_events(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all non-deleted managed events for a guild ordered by start time."""
        return await _list_events_cached(guild_id)

    async def get_managed_event(
        self, guild_id: int, event_id: int
    ) -> dict[str, object | None] | None:
        """Return one non-deleted managed event by local DB ID, or None if not found."""
        return await Database.get_managed_event(guild_id, event_id)

    async def upsert_from_discord(
        self, guild_id: int, event_data: dict[str, object | None]
    ) -> dict[str, object | None]:
        """Upsert a managed event from a Discord payload (uses discord_event_id as key)."""
        invalidate_events_cache(guild_id)
        return await Database.upsert_managed_event_from_discord(guild_id, event_data)

    async def create(
        self,
        guild_id: int,
        event_data: dict[str, object | None],
        created_by_user_id: str | None = None,
        created_by_name: str | None = None,
    ) -> dict[str, object | None]:
        """Create a new managed event row with pending projection state."""
        invalidate_events_cache(guild_id)
        return await Database.create_managed_event(
            guild_id=guild_id,
            payload=event_data,
            created_by_user_id=created_by_user_id,
            created_by_name=created_by_name,
        )

    async def update(
        self,
        guild_id: int,
        event_id: int,
        event_data: dict[str, object | None],
        updated_by_user_id: str | None = None,
        updated_by_name: str | None = None,
    ) -> dict[str, object | None] | None:
        """Update managed event fields and mark as pending projection.

        Returns the updated event dict, or None if the event was not found.
        """
        invalidate_events_cache(guild_id)
        return await Database.update_managed_event(
            guild_id=guild_id,
            event_id=event_id,
            payload=event_data,
            updated_by_user_id=updated_by_user_id,
            updated_by_name=updated_by_name,
        )

    async def delete(
        self,
        guild_id: int,
        event_id: int,
        deleted_by_user_id: str | None = None,
        deleted_by_name: str | None = None,
    ) -> bool:
        """Soft-delete a managed event row. Returns True if a row was deleted."""
        invalidate_events_cache(guild_id)
        return await Database.delete_managed_event(
            guild_id=guild_id,
            event_id=event_id,
            updated_by_user_id=deleted_by_user_id,
            updated_by_name=deleted_by_name,
        )

    async def list_active_events(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return active/upcoming/recurring events for a guild.

        Regular guild members must only ever see these; past events are filtered
        out here so visibility is enforced server-side rather than relying on the
        frontend. See ``is_active_event`` for the filtering rules and the
        channel-permission extension point.
        """
        events = await _list_events_cached(guild_id)
        return [event for event in events if is_active_event(event)]

    async def update_settings(
        self,
        guild_id: int,
        event_id: int,
        settings: dict[str, object | None],
        updated_by_user_id: str | None = None,
        updated_by_name: str | None = None,
    ) -> dict[str, object | None] | None:
        """Update event-level signup settings without touching event content.

        Recognized keys: signups_enabled, signups_closed, allow_multiple_roles,
        signup_channel_id. Only keys present in ``settings`` are changed. Returns
        the updated event dict, or None if the event does not exist.
        """
        allowed = {
            "signups_enabled": bool,
            "signups_closed": bool,
            "allow_multiple_roles": bool,
            "signup_channel_id": "raw",
        }
        set_clauses: list[str] = []
        params: list[object | None] = []
        for key, kind in allowed.items():
            if key not in settings:
                continue
            value = settings[key]
            if kind is bool:
                value = 1 if value else 0
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return await Database.get_managed_event(guild_id, event_id)

        set_clauses.append("updated_at = ?")
        params.append(int(time.time()))
        if updated_by_user_id is not None:
            set_clauses.append("updated_by_user_id = ?")
            params.append(updated_by_user_id)
        if updated_by_name is not None:
            set_clauses.append("updated_by_name = ?")
            params.append(updated_by_name)
        params.extend([guild_id, event_id])

        async with Database.get_connection() as db:
            cursor = await db.execute(
                f"UPDATE managed_events SET {', '.join(set_clauses)} "
                "WHERE guild_id = ? AND id = ? AND deleted_at IS NULL",
                tuple(params),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None
        invalidate_events_cache(guild_id)
        return await Database.get_managed_event(guild_id, event_id)

    async def get_pending_sync(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all non-deleted managed events for a guild that have pending sync status.

        These are events created or updated in the DB that have not yet been
        projected to Discord.
        """
        # TODO: add Database.list_managed_events_pending_sync(guild_id) that
        # filters on sync_status = 'pending'. For now, filter in Python.
        all_events = await Database.list_managed_events_by_guild(guild_id)
        return [e for e in all_events if e.get("sync_status") == "pending"]
