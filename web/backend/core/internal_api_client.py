from __future__ import annotations

"""
Internal API client for service-to-service calls to the bot's internal HTTP API.

Provides the ``InternalAPIClient`` class, helper error translators, and the
module-level singleton getter ``get_internal_api_client()``.
"""

import logging
import os
from typing import TypedDict

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Configurable timeout for internal API calls
INTERNAL_API_TIMEOUT_SECONDS = float(os.getenv("INTERNAL_API_TIMEOUT_SECONDS", "15"))

# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_internal_api_client: InternalAPIClient | None = None


def get_internal_api_client() -> InternalAPIClient:
    """Return the cached :class:`InternalAPIClient` instance."""
    global _internal_api_client
    if _internal_api_client is None:
        _internal_api_client = InternalAPIClient()
    return _internal_api_client


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _extract_internal_api_detail(response: httpx.Response) -> str | None:
    """Try to pull a useful error message out of an internal API response."""
    if response is None:
        return None

    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or None

    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, dict):
                nested = value.get("message")
                if nested:
                    return nested
            elif value:
                return str(value)
    elif isinstance(payload, str) and payload:
        return payload

    return None


def translate_internal_api_error(exc: Exception, default_detail: str) -> HTTPException:
    """Convert httpx exceptions into FastAPI-friendly :class:`HTTPException` objects."""
    if isinstance(exc, httpx.HTTPStatusError):
        detail = _extract_internal_api_detail(exc.response) or default_detail
        return HTTPException(status_code=exc.response.status_code, detail=detail)

    if isinstance(exc, httpx.RequestError):
        return HTTPException(status_code=503, detail=f"{default_detail}: {exc!s}")

    return HTTPException(status_code=500, detail=f"{default_detail}: {exc!s}")


# ---------------------------------------------------------------------------
# Typed request bodies
# ---------------------------------------------------------------------------


class RecheckRequestBody(TypedDict, total=False):
    """Request payload for member recheck."""

    log_leadership: bool
    admin_user_id: str


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------


class InternalAPIClient:
    """
    HTTP client for calling the bot's internal API.

    Handles authentication and provides typed methods for internal endpoints.
    """

    def __init__(self) -> None:
        from .env_config import INTERNAL_API_KEY, INTERNAL_API_URL

        self.base_url = INTERNAL_API_URL
        self.api_key = INTERNAL_API_KEY
        self._client: httpx.AsyncClient | None = None

        if self.api_key:
            logger.debug("InternalAPIClient initialized with authentication enabled")
        else:
            logger.warning(
                "InternalAPIClient initialized without INTERNAL_API_KEY; "
                "internal API calls may be unauthorized"
            )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers: dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=INTERNAL_API_TIMEOUT_SECONDS,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_bot_owner_ids(self) -> list[int]:
        """
        Fetch bot owner IDs from internal API.

        Supports single owner, team owners, and environment overrides.

        Returns:
            list of Discord user IDs who are bot owners

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.get("/bot-owner-ids")
        response.raise_for_status()
        payload = response.json()
        return payload.get("owner_ids", [])

    async def get_health_report(self) -> dict:
        """Get comprehensive health report from internal API."""
        client = await self._get_client()
        response = await client.get("/health/report")
        response.raise_for_status()
        return response.json()

    async def get_last_errors(self, limit: int = 1) -> dict:
        """Get most recent error log entries."""
        client = await self._get_client()
        response = await client.get("/errors/last", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def export_logs(self, max_bytes: int = 1048576) -> bytes:
        """Export bot logs as downloadable content."""
        client = await self._get_client()
        response = await client.get("/logs/export", params={"max_bytes": max_bytes})
        response.raise_for_status()
        return response.content

    async def get_guilds(self) -> list[dict]:
        """Fetch guilds where the bot is currently installed."""
        client = await self._get_client()
        response = await client.get("/guilds")
        response.raise_for_status()
        payload = response.json()
        return payload.get("guilds", [])

    async def get_guild_channels(self, guild_id: int) -> list[dict]:
        """Fetch text channels for a guild from internal API."""
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/channels")
        response.raise_for_status()
        payload = response.json()
        return payload.get("channels", [])

    async def get_guild_scheduled_events(self, guild_id: int) -> list[dict]:
        """Fetch scheduled events for a guild from the internal API."""
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/events/scheduled")
        response.raise_for_status()
        payload = response.json()
        return payload.get("events", [])

    async def get_guild_scheduled_event(
        self, guild_id: int, event_id: int
    ) -> dict:
        """Fetch a single scheduled event by ID from the internal API."""
        client = await self._get_client()
        response = await client.get(
            f"/guilds/{guild_id}/events/scheduled/{event_id}"
        )
        response.raise_for_status()
        return response.json().get("event", {})

    async def create_guild_scheduled_event(
        self, guild_id: int, payload: dict
    ) -> dict:
        """Create a scheduled event for a guild through the internal API."""
        client = await self._get_client()
        response = await client.post(
            f"/guilds/{guild_id}/events/scheduled", json=payload
        )
        response.raise_for_status()
        return response.json().get("event", {})

    async def update_guild_scheduled_event(
        self, guild_id: int, event_id: int, payload: dict
    ) -> dict:
        """Update a scheduled event for a guild through the internal API."""
        client = await self._get_client()
        response = await client.put(
            f"/guilds/{guild_id}/events/scheduled/{event_id}", json=payload
        )
        response.raise_for_status()
        return response.json().get("event", {})

    async def delete_guild_scheduled_event(self, guild_id: int, event_id: int) -> dict:
        """Delete a scheduled event for a guild through the internal API."""
        client = await self._get_client()
        response = await client.delete(
            f"/guilds/{guild_id}/events/scheduled/{event_id}"
        )
        response.raise_for_status()
        return response.json()

    async def get_guild_roles(self, guild_id: int) -> list[dict]:
        """Fetch Discord roles for a guild."""
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/roles")
        response.raise_for_status()
        payload = response.json()
        return payload.get("roles", [])

    async def get_guild_stats(self, guild_id: int) -> dict:
        """
        Fetch basic statistics for a guild (member count, etc).

        Returns:
            dict with keys: guild_id, member_count, approximate_member_count
        """
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/stats")
        response.raise_for_status()
        return response.json()

    async def get_guild_members(
        self, guild_id: int, page: int = 1, page_size: int = 100
    ) -> dict:
        """
        Fetch paginated list of guild members with Discord enrichment.

        Args:
            guild_id: Discord guild ID
            page: Page number (1-indexed)
            page_size: Items per page (max 1000)

        Returns:
            dict with keys: members (list), page, page_size, total
        """
        client = await self._get_client()
        response = await client.get(
            f"/guilds/{guild_id}/members", params={"page": page, "page_size": page_size}
        )
        response.raise_for_status()
        return response.json()

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict:
        """
        Fetch single guild member with Discord enrichment.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            dict with member data
        """
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/members/{user_id}")
        response.raise_for_status()
        return response.json()

    async def recheck_user(
        self,
        guild_id: int,
        user_id: int,
        admin_user_id: str | None = None,
        log_leadership: bool = True,
    ) -> dict:
        """
        Trigger reverification check for a specific user.

        Calls the bot's internal recheck endpoint to re-validate
        the user's RSI organization membership and update roles.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            admin_user_id: Optional Discord user ID of admin triggering recheck
            log_leadership: Whether to post individual leadership log message (default True)

        Returns:
            dict with recheck results (message, roles_updated, status, diff, etc.)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        json_body: RecheckRequestBody = {"log_leadership": log_leadership}
        if admin_user_id:
            json_body["admin_user_id"] = admin_user_id

        response = await client.post(
            f"/guilds/{guild_id}/members/{user_id}/recheck",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def notify_guild_settings_refresh(
        self, guild_id: int, source: str | None = None
    ) -> dict:
        """Notify the bot that guild configuration has changed."""
        client = await self._get_client()
        json_body = {"source": source} if source else None
        response = await client.post(
            f"/guilds/{guild_id}/config/refresh",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def resend_verification_message(self, guild_id: int) -> dict:
        """Trigger the bot to resend the verification message for a guild."""
        client = await self._get_client()
        response = await client.post(f"/guilds/{guild_id}/verification/resend")
        response.raise_for_status()
        return response.json()

    async def deploy_ticket_panel(
        self, guild_id: int, *, channel_id: str | None = None
    ) -> dict:
        """Ask the bot to deploy (or refresh) ticket panels.

        Args:
            guild_id: Discord guild ID.
            channel_id: If provided, deploy to this specific channel only.
        """
        client = await self._get_client()
        params: dict[str, str] = {}
        if channel_id:
            params["channel_id"] = channel_id
        response = await client.post(
            f"/guilds/{guild_id}/tickets/deploy-panel", params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_voice_channel_members(self, voice_channel_id: int) -> list[int]:
        """
        Get member IDs currently in a voice channel via bot's gateway cache.

        Args:
            voice_channel_id: Discord voice channel ID

        Returns:
            list of member IDs in the channel

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.get(f"/voice/members/{voice_channel_id}")
        response.raise_for_status()
        payload = response.json()
        return payload.get("member_ids", [])

    async def get_occupied_voice_channels(self, guild_id: int) -> list[dict]:
        """Fetch all occupied voice/stage channels for a guild.

        Only returns channels that have at least one human (non-bot) member.
        Data comes from Discord gateway cache — no API overhead.

        Args:
            guild_id: Discord guild ID

        Returns:
            list of channel dicts with member info

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/voice/occupied")
        response.raise_for_status()
        payload = response.json()
        return payload.get("channels", [])

    async def post_bulk_recheck_summary(
        self,
        guild_id: int,
        admin_user_id: int,
        scope_label: str,
        status_rows: list[dict],
        csv_bytes: str,
        csv_filename: str,
    ) -> dict:
        """
        Post bulk recheck summary to leadership channel.

        Args:
            guild_id: Discord guild ID
            admin_user_id: Discord user ID of admin who triggered recheck
            scope_label: Description of recheck scope (e.g., "web bulk recheck")
            status_rows: List of StatusRow data as dicts
            csv_bytes: Base64-encoded CSV file content
            csv_filename: Name for the CSV file

        Returns:
            dict with keys: success, channel_name, channel_mention

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        json_body = {
            "admin_user_id": admin_user_id,
            "scope_label": scope_label,
            "status_rows": status_rows,
            "csv_bytes": csv_bytes,
            "csv_filename": csv_filename,
        }
        response = await client.post(
            f"/guilds/{guild_id}/bulk-recheck/summary",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def leave_guild(self, guild_id: int) -> dict:
        """
        Make the bot leave a guild.

        This is a privileged operation - caller must validate bot owner permissions.

        Args:
            guild_id: Discord guild ID to leave

        Returns:
            dict with keys: success, guild_id, guild_name

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.post(f"/guilds/{guild_id}/leave")
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Metrics endpoints
    # ------------------------------------------------------------------

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
