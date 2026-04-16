"""DB-first event management service for dashboard workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.db.database import Database


class InternalEventProjectionClient(Protocol):
    """Subset of internal API operations required for event projection sync."""

    async def get_guild_scheduled_events(self, guild_id: int) -> list[dict]:
        """Fetch scheduled events from Discord via internal API."""
        ...

    async def create_guild_scheduled_event(self, guild_id: int, payload: dict) -> dict:
        """Create one scheduled event in Discord via internal API."""
        ...

    async def update_guild_scheduled_event(
        self, guild_id: int, event_id: int, payload: dict
    ) -> dict:
        """Update one scheduled event in Discord via internal API."""
        ...


@dataclass(slots=True)
class SyncResult:
    """Result counters for manual event synchronization operations."""

    processed: int = 0
    updated: int = 0


class EventService:
    """Application service for DB-first event management and sync orchestration."""

    @staticmethod
    async def list_events(guild_id: int) -> list[dict[str, object | None]]:
        """Return all managed events from DB for a guild."""
        return await Database.list_managed_events_by_guild(guild_id)

    @staticmethod
    async def get_event(
        guild_id: int, event_id: int
    ) -> dict[str, object | None] | None:
        """Return one managed event from DB for a guild."""
        return await Database.get_managed_event(guild_id, event_id)

    @staticmethod
    async def create_event(
        guild_id: int,
        payload: dict[str, object | None],
        created_by_user_id: str | None,
        created_by_name: str | None,
    ) -> dict[str, object | None]:
        """Create event in DB first (source of truth)."""
        return await Database.create_managed_event(
            guild_id=guild_id,
            payload=payload,
            created_by_user_id=created_by_user_id,
            created_by_name=created_by_name,
        )

    @staticmethod
    async def update_event(
        guild_id: int,
        event_id: int,
        payload: dict[str, object | None],
        updated_by_user_id: str | None,
        updated_by_name: str | None,
    ) -> dict[str, object | None] | None:
        """Update event in DB first and mark pending projection."""
        return await Database.update_managed_event(
            guild_id=guild_id,
            event_id=event_id,
            payload=payload,
            updated_by_user_id=updated_by_user_id,
            updated_by_name=updated_by_name,
        )

    @staticmethod
    def _to_projection_payload(event: dict[str, object | None]) -> dict[str, object | None]:
        """Convert DB event fields to internal API payload format."""
        return {
            "name": event.get("name"),
            "description": event.get("description"),
            "announcement_message": event.get("announcement_message"),
            "scheduled_start_time": event.get("scheduled_start_time"),
            "scheduled_end_time": event.get("scheduled_end_time"),
            "entity_type": event.get("entity_type") or "voice",
            "channel_id": event.get("channel_id"),
            "location": event.get("location"),
            "announcement_channel_id": event.get("announcement_channel_id"),
            "signup_role_ids": event.get("signup_role_ids") or [],
            "created_by_name": event.get("creator_name"),
        }

    @staticmethod
    async def sync_db_event_to_discord(
        guild_id: int,
        event: dict[str, object | None],
        projection_client: InternalEventProjectionClient,
    ) -> dict[str, object | None]:
        """Project one DB event to Discord and update sync state."""
        local_event_id = int(str(event["id"]))
        payload = EventService._to_projection_payload(event)
        discord_event_id = event.get("discord_event_id")

        try:
            if isinstance(discord_event_id, str) and discord_event_id.strip():
                projected_event = await projection_client.update_guild_scheduled_event(
                    guild_id,
                    int(discord_event_id),
                    payload,
                )
                operation = "update"
            else:
                projected_event = await projection_client.create_guild_scheduled_event(
                    guild_id,
                    payload,
                )
                operation = "create"

            projected_id_raw = projected_event.get("id")
            projected_id = str(projected_id_raw) if projected_id_raw is not None else None
            await Database.mark_managed_event_synced(
                guild_id=guild_id,
                event_id=local_event_id,
                discord_event_id=projected_id,
            )
            await Database.record_managed_event_sync_audit(
                guild_id=guild_id,
                event_id=local_event_id,
                direction="push",
                operation=operation,
                status="success",
                detail=None,
            )
        except Exception as exc:
            await Database.mark_managed_event_sync_failed(
                guild_id=guild_id,
                event_id=local_event_id,
                error_message=str(exc),
            )
            await Database.record_managed_event_sync_audit(
                guild_id=guild_id,
                event_id=local_event_id,
                direction="push",
                operation="upsert",
                status="error",
                detail=str(exc),
            )
            raise

        latest_event = await Database.get_managed_event(guild_id, local_event_id)
        if latest_event is None:
            raise RuntimeError("Managed event disappeared after sync")
        return latest_event

    @staticmethod
    async def manual_sync(
        guild_id: int,
        direction: str,
        projection_client: InternalEventProjectionClient,
        event_id: int | None = None,
    ) -> tuple[SyncResult, list[dict[str, object | None]]]:
        """Run manual sync in requested direction and return latest event states."""
        result = SyncResult()

        if direction in {"pull", "reconcile"}:
            discord_events = await projection_client.get_guild_scheduled_events(guild_id)
            for discord_event in discord_events:
                result.processed += 1
                await Database.upsert_managed_event_from_discord(guild_id, discord_event)
                result.updated += 1

        if direction in {"push", "reconcile"}:
            managed_events = await Database.list_managed_events_by_guild(guild_id)
            for managed_event in managed_events:
                local_event_id = int(str(managed_event["id"]))
                if event_id is not None and local_event_id != event_id:
                    continue
                result.processed += 1
                await EventService.sync_db_event_to_discord(
                    guild_id,
                    managed_event,
                    projection_client,
                )
                result.updated += 1

        latest_events = await Database.list_managed_events_by_guild(guild_id)
        return result, latest_events
