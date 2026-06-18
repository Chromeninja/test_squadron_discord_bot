"""Metrics and activity methods for InternalAPIClient."""

from __future__ import annotations

import httpx

__all__ = ["MetricsMixin"]


class MetricsMixin:
    """Mixin providing metrics and activity group endpoints for InternalAPIClient."""

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (provided by main class)."""
        raise NotImplementedError

    async def get_metrics_overview(
        self, guild_id: int, days: int = 7, user_ids: list[int] | None = None
    ) -> dict:
        """Get metrics overview (live snapshot + aggregated period data)."""
        client = await self._get_client()
        params: dict = {"days": days}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/overview", params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_metrics_voice_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Get top users by voice time."""
        client = await self._get_client()
        params: dict = {"days": days, "limit": limit}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/voice/leaderboard",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_metrics_message_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Get top users by message count."""
        client = await self._get_client()
        params: dict = {"days": days, "limit": limit}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/messages/leaderboard",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_metrics_top_games(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Get top games by total play time."""
        client = await self._get_client()
        params: dict = {"days": days, "limit": limit}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/games/top",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_metrics_game(
        self,
        guild_id: int,
        game_name: str,
        days: int = 7,
        limit: int = 5,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Get detailed metrics for a specific game."""
        client = await self._get_client()
        params: dict = {"game_name": game_name, "days": days, "limit": limit}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/games/detail",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_metrics_timeseries(
        self,
        guild_id: int,
        metric: str = "messages",
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Get hourly time-series data for charts."""
        client = await self._get_client()
        params: dict = {"metric": metric, "days": days}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/timeseries",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_metrics_user(
        self, guild_id: int, user_id: int, days: int = 7
    ) -> dict:
        """Get detailed metrics for a specific user."""
        client = await self._get_client()
        response = await client.get(
            f"/guilds/{guild_id}/metrics/user/{user_id}",
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()

    async def delete_metrics_user(self, guild_id: int, user_id: int) -> dict:
        """Delete all metrics data for a specific user (data erasure)."""
        client = await self._get_client()
        response = await client.delete(f"/guilds/{guild_id}/metrics/user/{user_id}")
        response.raise_for_status()
        return response.json()

    async def get_activity_groups(
        self,
        guild_id: int,
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Get activity group tier counts per dimension."""
        client = await self._get_client()
        params: dict[str, int | str] = {"days": days}
        if user_ids is not None:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
        response = await client.get(
            f"/guilds/{guild_id}/metrics/activity-groups",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_activity_group_members(
        self, guild_id: int, dimension: str, tier: str
    ) -> dict:
        """Get user IDs for a specific dimension+tier activity group."""
        client = await self._get_client()
        response = await client.get(
            f"/guilds/{guild_id}/metrics/activity-group-members",
            params={"dimension": dimension, "tier": tier},
        )
        response.raise_for_status()
        return response.json()

    async def get_activity_group_members_bulk(
        self,
        guild_id: int,
        dimensions: list[str],
        tiers: list[str],
        days: int = 30,
    ) -> dict[str, dict[str, list[int]]]:
        """Get user IDs for multiple dimension+tier combos in one call.

        Returns ``{dimension: {tier: [user_id, ...], ...}, ...}``.
        """
        client = await self._get_client()
        response = await client.get(
            f"/guilds/{guild_id}/metrics/activity-group-members-bulk",
            params={
                "dimensions": ",".join(dimensions),
                "tiers": ",".join(tiers),
                "days": str(days),
            },
        )
        response.raise_for_status()
        return response.json()
