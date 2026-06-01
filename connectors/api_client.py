"""
HTTP client for bot→backend communication.
All requests use X-Bot-Api-Key auth (set BOT_API_KEY env var, same value in backend).
"""

import asyncio
import logging
import os
from typing import Any, TypeVar

import httpx

T = TypeVar("T")
log = logging.getLogger(__name__)


class BotAPIConnector:
    """Thin httpx wrapper with retry logic and structured error handling."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.environ.get(
            "BACKEND_URL", "http://localhost:8000"
        )
        self._api_key = api_key or os.environ.get("BOT_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Bot-Api-Key": self._api_key},
            timeout=10.0,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return await self._request("POST", path, json=json, **kwargs)

    async def patch(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return await self._request("PATCH", path, json=json, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self._request("DELETE", path, **kwargs)

    async def _request(
        self, method: str, path: str, retries: int = 3, **kwargs: Any
    ) -> Any:
        """Execute request with exponential backoff retry (network errors only)."""
        for attempt in range(retries):
            try:
                assert self._client is not None, "Call start() before making requests"
                response = await self._client.request(method, path, **kwargs)
                response.raise_for_status()
                if response.content:
                    return response.json()
                return None
            except httpx.HTTPStatusError as e:
                # Don't retry 4xx/5xx status errors — the request reached the backend.
                log.exception(
                    "Backend returned %s for %s %s",
                    e.response.status_code,
                    method,
                    path,
                )
                raise
            except (httpx.ConnectError, httpx.TimeoutException):
                if attempt == retries - 1:
                    log.exception(
                        "Backend unreachable after %d attempts: %s %s",
                        retries,
                        method,
                        path,
                    )
                    raise
                wait = 2**attempt  # 1s, 2s, 4s
                log.warning(
                    "Backend request failed (attempt %d/%d), retrying in %ds",
                    attempt + 1,
                    retries,
                    wait,
                )
                await asyncio.sleep(wait)
