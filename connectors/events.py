"""Connector for bot→backend event operations (/internal/guilds/{guild_id}/events)."""

from .api_client import BotAPIConnector


class EventsConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def list_events(self, guild_id: int) -> list[dict]:
        return await self._c.get(f"/internal/guilds/{guild_id}/events") or []

    async def sync_from_discord(self, guild_id: int) -> dict:
        """Trigger a pull-sync from Discord into the DB via backend."""
        return await self._c.post(
            f"/internal/guilds/{guild_id}/events/sync", json={"direction": "pull"}
        )

    async def push_to_discord(self, guild_id: int, event_id: int) -> dict:
        return await self._c.post(
            f"/internal/guilds/{guild_id}/events/{event_id}/sync",
            json={"direction": "push"},
        )
