"""Connector for bot→backend managed-event operations.

Backend routes live under /internal/guilds/{guild_id}/managed-events and own the
DB state for managed events (CRUD + a pending-sync flag). Projecting that state
onto Discord ("sync") is bot-side work and is NOT a backend call — the bot reads
pending events via ``list_pending_sync`` and projects them itself.
"""

from .api_client import BotAPIConnector


class EventsConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def list_events(self, guild_id: int) -> list[dict]:
        """Return all non-deleted managed events for a guild."""
        resp = await self._c.get(f"/internal/guilds/{guild_id}/managed-events")
        return (resp or {}).get("events", [])

    async def list_pending_sync(self, guild_id: int) -> list[dict]:
        """Return managed events that have not yet been projected to Discord."""
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/managed-events/pending-sync"
        )
        return (resp or {}).get("events", [])

    async def get_event(self, guild_id: int, event_id: int) -> dict | None:
        """Return a single managed event by local DB id, or None if not found."""
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/managed-events/{event_id}"
        )
        return (resp or {}).get("event")

    async def create_event(self, guild_id: int, data: dict) -> dict:
        resp = await self._c.post(
            f"/internal/guilds/{guild_id}/managed-events", json=data
        )
        return (resp or {}).get("event", {})

    async def update_event(self, guild_id: int, event_id: int, data: dict) -> dict:
        resp = await self._c.patch(
            f"/internal/guilds/{guild_id}/managed-events/{event_id}", json=data
        )
        return (resp or {}).get("event", {})

    async def delete_event(self, guild_id: int, event_id: int) -> bool:
        resp = await self._c.delete(
            f"/internal/guilds/{guild_id}/managed-events/{event_id}"
        )
        return bool((resp or {}).get("success"))

    async def upsert_from_discord(self, guild_id: int, data: dict) -> dict:
        """Upsert a managed event from a Discord event payload (keyed on discord_event_id)."""
        resp = await self._c.post(
            f"/internal/guilds/{guild_id}/managed-events/upsert-from-discord",
            json=data,
        )
        return (resp or {}).get("event", {})
