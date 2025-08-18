# helpers/http_helper.py

import aiohttp
import asyncio
from typing import Optional
from helpers.logger import get_logger

logger = get_logger(__name__)


class NotFoundError(Exception):
    """Raised when a 404 is encountered and the caller should treat the resource as gone."""
    pass

class HTTPClient:
    def __init__(self, timeout: int = 15, concurrency: int = 8):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._sem = asyncio.Semaphore(concurrency)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout, raise_for_status=False)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_html(self, url: str) -> Optional[str]:
        """
        GET HTML with light rate limiting and clear error semantics:
          - 200: returns text
          - 404: raises NotFoundError (caller can prune / stop retrying)
          - Other 4xx/5xx: returns None (transient or generic failure)
        """
        async with self._sem:
            session = await self._get_session()
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0 TESTBot"}) as resp:
                    status = resp.status
                    if status == 200:
                        text = await resp.text()
                        logger.debug(f"Fetched {url} ({len(text)} bytes)")
                        return text
                    if status == 404:
                        logger.warning(f"Fetch {url} -> HTTP 404 (client error), not retrying")
                        # This is a permanent "gone" state for RSI handles; let callers react accordingly.
                        raise NotFoundError("404")
                    # Treat other statuses as transient / generic failures
                    logger.warning(f"HTTP {status} for {url}")
                    return None
            except asyncio.TimeoutError:
                logger.warning(f"Timeout while fetching {url}")
                return None
            except aiohttp.ClientError as e:
                logger.warning(f"Client error while fetching {url}: {e}")
                return None