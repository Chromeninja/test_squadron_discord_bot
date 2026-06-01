"""Connector for bot→backend metrics operations (/internal/guilds/{guild_id}/metrics)."""

from .api_client import BotAPIConnector


class MetricsConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def track(self, guild_id: int, event_type: str, data: dict) -> dict | None:
        """Record a metrics event to the backend."""
        return await self._c.post(
            f"/internal/guilds/{guild_id}/metrics/track",
            json={"event_type": event_type, **data},
        )

    async def get_overview(self, guild_id: int, days: int = 7) -> dict:
        return await self._c.get(
            f"/internal/guilds/{guild_id}/metrics/overview", params={"days": days}
        )

    async def get_voice_leaderboard(
        self, guild_id: int, days: int = 7, limit: int = 10
    ) -> dict:
        return await self._c.get(
            f"/internal/guilds/{guild_id}/metrics/voice/leaderboard",
            params={"days": days, "limit": limit},
        )

    async def get_message_leaderboard(
        self, guild_id: int, days: int = 7, limit: int = 10
    ) -> dict:
        return await self._c.get(
            f"/internal/guilds/{guild_id}/metrics/messages/leaderboard",
            params={"days": days, "limit": limit},
        )

    async def delete_user_data(self, guild_id: int, user_id: int) -> dict:
        """Delete all metrics data for a user (data erasure)."""
        return await self._c.delete(
            f"/internal/guilds/{guild_id}/metrics/user/{user_id}"
        )
