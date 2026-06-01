"""Connector for bot→backend voice operations (/internal/guilds/{guild_id}/voice)."""

from .api_client import BotAPIConnector


class VoiceConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    async def get_jtc_channels(self, guild_id: int) -> list[dict]:
        return await self._c.get(f"/internal/guilds/{guild_id}/voice/jtc") or []

    async def get_voice_channel(self, guild_id: int, channel_id: int) -> dict | None:
        try:
            return await self._c.get(
                f"/internal/guilds/{guild_id}/voice/channels/{channel_id}"
            )
        except Exception:
            return None

    async def create_voice_channel(self, guild_id: int, data: dict) -> dict:
        return await self._c.post(
            f"/internal/guilds/{guild_id}/voice/channels", json=data
        )

    async def update_voice_channel(
        self, guild_id: int, channel_id: int, data: dict
    ) -> dict:
        return await self._c.patch(
            f"/internal/guilds/{guild_id}/voice/channels/{channel_id}", json=data
        )

    async def delete_voice_channel(self, guild_id: int, channel_id: int) -> None:
        await self._c.delete(f"/internal/guilds/{guild_id}/voice/channels/{channel_id}")

    # ── Cooldown ─────────────────────────────────────────────────────────────

    async def check_cooldown(
        self,
        guild_id: int,
        jtc_channel_id: int,
        user_id: int,
        cooldown_seconds: int = 5,
    ) -> bool:
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/voice/cooldown/{jtc_channel_id}/{user_id}",
            params={"cooldown_seconds": cooldown_seconds},
        )
        return bool((resp or {}).get("on_cooldown", False))

    async def update_cooldown(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> None:
        await self._c.post(
            f"/internal/guilds/{guild_id}/voice/cooldown/{jtc_channel_id}/{user_id}"
        )

    # ── Ownership queries ────────────────────────────────────────────────────

    async def get_user_channel_in_jtc(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> int | None:
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/voice/channels/user/{user_id}/jtc/{jtc_channel_id}"
        )
        return (resp or {}).get("voice_channel_id")

    async def get_any_user_channel(self, guild_id: int, user_id: int) -> int | None:
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/voice/channels/user/{user_id}"
        )
        return (resp or {}).get("voice_channel_id")

    async def get_user_channel_info(
        self, guild_id: int, user_id: int
    ) -> dict | None:
        try:
            resp = await self._c.get(
                f"/internal/guilds/{guild_id}/voice/channels/user/{user_id}/info"
            )
            return (resp or {}).get("channel")
        except Exception:
            return None

    async def get_jtc_for_owned_channel(
        self, guild_id: int, voice_channel_id: int, owner_id: int
    ) -> int | None:
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/voice/channels/owned/{voice_channel_id}/jtc",
            params={"owner_id": owner_id},
        )
        return (resp or {}).get("jtc_channel_id")

    async def get_all_active_channels(self, guild_id: int) -> list[dict]:
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/voice/channels/active"
        )
        return (resp or {}).get("channels", [])

    async def get_active_channel_ids(self, guild_id: int) -> list[int]:
        resp = await self._c.get(
            f"/internal/guilds/{guild_id}/voice/channels/active/ids"
        )
        return (resp or {}).get("channel_ids", [])

    # ── Cleanup / purge ──────────────────────────────────────────────────────

    async def cleanup_channel_records(
        self, guild_id: int, channel_id: int
    ) -> None:
        await self._c.delete(
            f"/internal/guilds/{guild_id}/voice/channels/{channel_id}/records"
        )

    async def purge_voice_data(
        self, guild_id: int, user_id: int | None = None
    ) -> dict:
        payload: dict = {}
        if user_id is not None:
            payload["user_id"] = user_id
        resp = await self._c.delete(
            f"/internal/guilds/{guild_id}/voice/purge", json=payload
        )
        return (resp or {}).get("deleted", {})

    async def purge_stale_jtc_data(
        self, guild_id: int, stale_jtc_ids: set[int]
    ) -> dict:
        resp = await self._c.delete(
            f"/internal/guilds/{guild_id}/voice/jtc/purge",
            json={"stale_jtc_ids": list(stale_jtc_ids)},
        )
        return (resp or {}).get("deleted", {})
