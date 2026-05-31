"""Connector for bot→backend verification operations (/internal/guilds/{guild_id}/verification)."""
from .api_client import BotAPIConnector


class VerificationConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def get_status(self, guild_id: int, user_id: int) -> dict | None:
        try:
            return await self._c.get(
                f"/internal/guilds/{guild_id}/verification/members/{user_id}"
            )
        except Exception:
            return None

    async def verify_member(self, guild_id: int, user_id: int, data: dict) -> dict:
        return await self._c.post(
            f"/internal/guilds/{guild_id}/verification/members/{user_id}", json=data
        )

    async def recheck_member(self, guild_id: int, user_id: int, data: dict | None = None) -> dict:
        return await self._c.post(
            f"/internal/guilds/{guild_id}/verification/members/{user_id}/recheck",
            json=data or {},
        )

    async def resend_message(self, guild_id: int) -> dict:
        return await self._c.post(f"/internal/guilds/{guild_id}/verification/resend")

    async def get_config(self, guild_id: int) -> dict:
        return await self._c.get(f"/internal/guilds/{guild_id}/verification")
