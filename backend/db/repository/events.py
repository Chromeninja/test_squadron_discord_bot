"""EventRepository — thin wrapper around Database class for managed event queries.

This module extracts all event/managed_event DB query methods from
web/backend/core/event_service.py and services/db/managed_event_mapper.py
into a clean repository class that takes no direct aiosqlite connection —
it delegates to the existing Database class methods which handle their own
connections via the async context manager pattern.
"""

from __future__ import annotations

from services.db.database import Database


class EventRepository:
    """Repository for managed_events table operations.

    Takes no database instance in __init__ because the underlying Database
    class manages its own connection pool via the get_connection() context manager.
    The guild_id parameter is required on every method to ensure all queries
    are properly scoped to a single guild.
    """

    async def get_managed_events(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all non-deleted managed events for a guild ordered by start time."""
        return await Database.list_managed_events_by_guild(guild_id)

    async def get_managed_event(
        self, guild_id: int, event_id: int
    ) -> dict[str, object | None] | None:
        """Return one non-deleted managed event by local DB ID, or None if not found."""
        return await Database.get_managed_event(guild_id, event_id)

    async def upsert_from_discord(
        self, guild_id: int, event_data: dict[str, object | None]
    ) -> dict[str, object | None]:
        """Upsert a managed event from a Discord payload (uses discord_event_id as key)."""
        return await Database.upsert_managed_event_from_discord(guild_id, event_data)

    async def create(
        self,
        guild_id: int,
        event_data: dict[str, object | None],
        created_by_user_id: str | None = None,
        created_by_name: str | None = None,
    ) -> dict[str, object | None]:
        """Create a new managed event row with pending projection state."""
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
        return await Database.delete_managed_event(
            guild_id=guild_id,
            event_id=event_id,
            updated_by_user_id=deleted_by_user_id,
            updated_by_name=deleted_by_name,
        )

    async def get_pending_sync(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all non-deleted managed events for a guild that have pending sync status.

        These are events created or updated in the DB that have not yet been
        projected to Discord.
        """
        # TODO: add Database.list_managed_events_pending_sync(guild_id) that
        # filters on sync_status = 'pending'. For now, filter in Python.
        all_events = await Database.list_managed_events_by_guild(guild_id)
        return [e for e in all_events if e.get("sync_status") == "pending"]
