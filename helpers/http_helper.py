# helpers/http_helper.py

import aiohttp
import asyncio
import random
from typing import Optional
from aiolimiter import AsyncLimiter

from config.config_loader import ConfigLoader
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

class HTTPClient:
    """
    HTTP client for making asynchronous HTTP requests with a single ClientSession.
    Adds polite UA, per-host rate limit, and bounded retries.
    """

    def __init__(self):
        self.session = None
        self._limiter = None
        self._ua = None

    async def init_session(self):
        """
        Initializes the ClientSession.
        """
        if self.session is None:
            cfg = ConfigLoader.load_config()
            rsi_cfg = (cfg or {}).get("rsi", {}) or {}
            rpm = int(rsi_cfg.get("requests_per_minute", 30))
            self._ua = rsi_cfg.get("user_agent") or "TEST-Squadron-Verification-Bot/1.0"

            # limiter applies across all fetches (manual + auto)
            self._limiter = AsyncLimiter(max_rate=max(1, rpm), time_period=60)

            connector = aiohttp.TCPConnector(limit_per_host=10)
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {
                "User-Agent": self._ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.7",
                "Cache-Control": "no-cache"
            }
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers)

    async def fetch_html(self, url: str) -> Optional[str]:
        """
        Fetches HTML content from a given URL asynchronously with retries & rate-limiting.

        Returns:
            Optional[str]: The fetched HTML content as a string, or None if failed.
        """
        if self.session is None or self._limiter is None:
            logger.error("HTTPClient session not initialized.")
            return None

        # Bounded exponential backoff with jitter
        attempts = 0
        max_attempts = 3
        base = 0.6

        while attempts < max_attempts:
            attempts += 1
            try:
                async with self._limiter:
                    async with self.session.get(url) as response:
                        if response.status != 200:
                            logger.warning(f"Fetch {url} attempt {attempts} -> HTTP {response.status}")
                            # Retry on >=500; break on hard client errors
                            if response.status >= 500:
                                raise aiohttp.ClientResponseError(
                                    response.request_info, response.history, status=response.status
                                )
                            return None
                        return await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempts >= max_attempts:
                    logger.error(f"Failed to fetch {url} after {attempts} attempts: {e}")
                    return None
                # jittered sleep
                sleep_s = base * (2 ** (attempts - 1)) + random.uniform(0, 0.4)
                await asyncio.sleep(sleep_s)
            except Exception as e:
                logger.exception(f"Unexpected exception fetching {url}: {e}")
                return None

    async def close(self):
        """
        Closes the HTTP client session.
        """
        if self.session is not None:
            await self.session.close()
            self.session = None
