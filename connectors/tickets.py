"""Connector for bot→backend ticket operations (/internal/guilds/{guild_id}/tickets)."""

from .api_client import BotAPIConnector


class TicketsConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def list_tickets(self, guild_id: int) -> list[dict]:
        return await self._c.get(f"/internal/guilds/{guild_id}/tickets") or []

    async def get_ticket(self, guild_id: int, ticket_id: int) -> dict | None:
        try:
            return await self._c.get(f"/internal/guilds/{guild_id}/tickets/{ticket_id}")
        except Exception:
            return None

    async def create_ticket(self, guild_id: int, data: dict) -> dict:
        return await self._c.post(f"/internal/guilds/{guild_id}/tickets", json=data)

    async def update_ticket(self, guild_id: int, ticket_id: int, data: dict) -> dict:
        return await self._c.patch(
            f"/internal/guilds/{guild_id}/tickets/{ticket_id}", json=data
        )

    async def close_ticket(self, guild_id: int, ticket_id: int) -> dict:
        return await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/{ticket_id}/close"
        )

    async def delete_ticket(self, guild_id: int, ticket_id: int) -> None:
        await self._c.delete(f"/internal/guilds/{guild_id}/tickets/{ticket_id}")
