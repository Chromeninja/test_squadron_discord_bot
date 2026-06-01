"""Connector for bot→backend ticket operations (/internal/guilds/{guild_id}/tickets)."""

from .api_client import BotAPIConnector


class TicketsConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def list_tickets(self, guild_id: int) -> list[dict]:
        result = await self._c.get(f"/internal/guilds/{guild_id}/tickets")
        return result.get("tickets", []) if isinstance(result, dict) else []

    async def get_ticket(self, guild_id: int, ticket_id: int) -> dict | None:
        try:
            result = await self._c.get(f"/internal/guilds/{guild_id}/tickets/{ticket_id}")
            return result.get("ticket") if isinstance(result, dict) else result
        except Exception:
            return None

    async def create_ticket(self, guild_id: int, data: dict) -> dict:
        result = await self._c.post(f"/internal/guilds/{guild_id}/tickets", json=data)
        return result.get("ticket", result) if isinstance(result, dict) else result

    async def update_ticket(self, guild_id: int, ticket_id: int, data: dict) -> dict:
        result = await self._c.patch(
            f"/internal/guilds/{guild_id}/tickets/{ticket_id}", json=data
        )
        return result.get("ticket", result) if isinstance(result, dict) else result

    async def close_ticket(self, guild_id: int, ticket_id: int) -> dict:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/{ticket_id}/close"
        )
        return result or {}

    async def delete_ticket(self, guild_id: int, ticket_id: int) -> None:
        await self._c.delete(f"/internal/guilds/{guild_id}/tickets/{ticket_id}")

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    async def list_categories(self, guild_id: int) -> list[dict]:
        result = await self._c.get(f"/internal/guilds/{guild_id}/ticket-categories")
        return result.get("categories", []) if isinstance(result, dict) else []

    async def get_category(self, guild_id: int, category_id: int) -> dict | None:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-categories/{category_id}"
            )
            return result.get("category") if isinstance(result, dict) else result
        except Exception:
            return None

    async def create_category(self, guild_id: int, data: dict) -> dict:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/ticket-categories", json=data
        )
        return result.get("category", result) if isinstance(result, dict) else result

    async def update_category(self, guild_id: int, category_id: int, data: dict) -> dict:
        result = await self._c.patch(
            f"/internal/guilds/{guild_id}/ticket-categories/{category_id}",
            json=data,
        )
        return result.get("category", result) if isinstance(result, dict) else result

    async def delete_category(self, guild_id: int, category_id: int) -> None:
        await self._c.delete(f"/internal/guilds/{guild_id}/ticket-categories/{category_id}")

    # ------------------------------------------------------------------
    # Channel Configs
    # ------------------------------------------------------------------

    async def list_channel_configs(self, guild_id: int) -> list[dict]:
        result = await self._c.get(f"/internal/guilds/{guild_id}/ticket-channels")
        return result.get("configs", []) if isinstance(result, dict) else []

    async def get_channel_config(self, guild_id: int, channel_id: int) -> dict | None:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-channels/{channel_id}"
            )
            return result.get("config") if isinstance(result, dict) else result
        except Exception:
            return None

    async def create_channel_config(self, guild_id: int, data: dict) -> dict:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/ticket-channels", json=data
        )
        return result.get("config", result) if isinstance(result, dict) else result

    async def update_channel_config(
        self, guild_id: int, channel_id: int, data: dict
    ) -> dict:
        result = await self._c.patch(
            f"/internal/guilds/{guild_id}/ticket-channels/{channel_id}",
            json=data,
        )
        return result.get("config", result) if isinstance(result, dict) else result

    async def delete_channel_config(self, guild_id: int, channel_id: int) -> None:
        await self._c.delete(f"/internal/guilds/{guild_id}/ticket-channels/{channel_id}")

    # ------------------------------------------------------------------
    # Ticket Queries & Actions
    # ------------------------------------------------------------------

    async def get_ticket_stats(self, guild_id: int) -> dict:
        result = await self._c.get(f"/internal/guilds/{guild_id}/tickets/stats")
        return result.get("stats", {}) if isinstance(result, dict) else {}

    async def get_ticket_by_thread(self, guild_id: int, thread_id: int) -> dict | None:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/tickets/by-thread/{thread_id}"
            )
            return result.get("ticket") if isinstance(result, dict) else result
        except Exception:
            return None

    async def claim_ticket(self, guild_id: int, thread_id: int, claimed_by: int) -> bool:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/by-thread/{thread_id}/claim",
            json={"claimed_by": claimed_by},
        )
        return result.get("claimed", False) if isinstance(result, dict) else False

    async def unclaim_ticket(self, guild_id: int, thread_id: int) -> bool:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/by-thread/{thread_id}/unclaim"
        )
        return result.get("unclaimed", False) if isinstance(result, dict) else False

    async def reopen_ticket(
        self, guild_id: int, thread_id: int, reopened_by: int
    ) -> bool:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/by-thread/{thread_id}/reopen",
            json={"reopened_by": reopened_by},
        )
        return result.get("reopened", False) if isinstance(result, dict) else False

    async def close_ticket_by_thread(
        self, guild_id: int, thread_id: int, closed_by: int, close_reason: str | None = None
    ) -> bool:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/by-thread/{thread_id}/close",
            json={"closed_by": closed_by, "close_reason": close_reason},
        )
        return result.get("closed", False) if isinstance(result, dict) else False

    async def mark_thread_deleted(self, guild_id: int, thread_id: int) -> bool:
        result = await self._c.post(
            f"/internal/guilds/{guild_id}/tickets/by-thread/{thread_id}/mark-deleted"
        )
        return result.get("marked", False) if isinstance(result, dict) else False

    # ------------------------------------------------------------------
    # Ticket Queries (Additional)
    # ------------------------------------------------------------------

    async def list_open_tickets(
        self, guild_id: int, user_id: int | None = None
    ) -> list[dict]:
        params = {}
        if user_id is not None:
            params["user_id"] = user_id
        result = await self._c.get(
            f"/internal/guilds/{guild_id}/tickets/open", params=params
        )
        return result.get("tickets", []) if isinstance(result, dict) else []

    async def list_categories_for_channel(
        self, guild_id: int, channel_id: int
    ) -> list[dict]:
        result = await self._c.get(
            f"/internal/guilds/{guild_id}/ticket-categories/by-channel/{channel_id}"
        )
        return result.get("categories", []) if isinstance(result, dict) else []
