"""Connector for bot→backend guild config operations (/internal/guilds/{guild_id}/config)."""

import httpx

from .api_client import BotAPIConnector


class ConfigConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def get_config(self, guild_id: int) -> dict:
        return await self._c.get(f"/internal/guilds/{guild_id}/config")

    async def update_config(self, guild_id: int, data: dict) -> dict:
        return await self._c.patch(f"/internal/guilds/{guild_id}/config", json=data)

    async def get_setting(self, guild_id: int, key: str) -> dict | None:
        """Return setting value or None for 404; all other errors propagate."""
        try:
            return await self._c.get(
                f"/internal/guilds/{guild_id}/config/settings/{key}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def set_setting(self, guild_id: int, key: str, value: object) -> dict:
        return await self._c.patch(
            f"/internal/guilds/{guild_id}/config/settings/{key}", json={"value": value}
        )

    async def get_guild_setting(self, guild_id: int, key: str) -> object | None:
        """Return the raw value for a single setting, or None if unset.

        Convenience wrapper over ``get_setting`` that unwraps the
        ``{"key", "value"}`` envelope to match the legacy
        ``ConfigService.get_guild_setting`` contract.
        """
        resp = await self.get_setting(guild_id, key)
        return resp.get("value") if resp else None

    async def notify_refresh(self, guild_id: int, source: str | None = None) -> dict:
        """Notify the backend that guild configuration has changed."""
        return await self._c.post(
            f"/internal/guilds/{guild_id}/config/refresh",
            json={"source": source} if source else {},
        )

    async def get_roles(self, guild_id: int) -> dict:
        """Get role configuration for a guild."""
        resp = await self._c.get(f"/internal/guilds/{guild_id}/config/roles")
        return (resp or {}).get("roles", {})

    async def get_channels(self, guild_id: int) -> dict:
        """Get channel configuration for a guild."""
        resp = await self._c.get(f"/internal/guilds/{guild_id}/config/channels")
        return (resp or {}).get("channels", {})

    async def get_jtc_channels(self, guild_id: int) -> list:
        """Get join-to-create voice channels for a guild."""
        resp = await self._c.get(f"/internal/guilds/{guild_id}/config/jtc-channels")
        return (resp or {}).get("channels", [])
