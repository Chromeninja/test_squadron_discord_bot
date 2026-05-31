"""Connector for bot→backend voice operations (/internal/guilds/{guild_id}/voice)."""
from .api_client import BotAPIConnector


class VoiceConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def get_jtc_channels(self, guild_id: int) -> list[dict]:
        return await self._c.get(f"/internal/guilds/{guild_id}/voice/jtc") or []

    async def get_voice_channel(self, guild_id: int, channel_id: int) -> dict | None:
        try:
            return await self._c.get(f"/internal/guilds/{guild_id}/voice/channels/{channel_id}")
        except Exception:
            return None

    async def create_voice_channel(self, guild_id: int, data: dict) -> dict:
        return await self._c.post(f"/internal/guilds/{guild_id}/voice/channels", json=data)

    async def update_voice_channel(self, guild_id: int, channel_id: int, data: dict) -> dict:
        return await self._c.patch(
            f"/internal/guilds/{guild_id}/voice/channels/{channel_id}", json=data
        )

    async def delete_voice_channel(self, guild_id: int, channel_id: int) -> None:
        await self._c.delete(f"/internal/guilds/{guild_id}/voice/channels/{channel_id}")
