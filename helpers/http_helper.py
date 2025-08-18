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
        self.session: Optional[aiohttp.ClientSession] = None
        self._limiter: Optional[AsyncLimiter] = None
        self._ua: str = "TEST-Squadron-Verification-Bot/1.0"

    async def init_session(self):
        """
        Initializes the ClientSession. Safe to call multiple times; will no-op if already initialized.
        """
        if self.session is not None:
            return

        cfg = ConfigLoader.load_config()
        rsi_cfg = (cfg or {}).get("rsi", {}) or {}
        rpm = int(rsi_cfg.get("requests_per_minute", 30))
        self._ua = rsi_cfg.get("user_agent") or self._ua

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
                        status = response.status
                        if status == 200:
                            return await response.text()

                        # 5xx -> transient, raise to trigger retry
                        if status >= 500:
                            logger.warning(f"Fetch {url} attempt {attempts} -> HTTP {status} (server error), will retry")
                            raise aiohttp.ClientResponseError(
                                response.request_info, response.history, status=response.status
                            )

                        # 4xx -> client error, do not retry
                        if 400 <= status < 500:
                            logger.warning(f"Fetch {url} -> HTTP {status} (client error), not retrying")
                            return None

                        # any other status -> treat as failure without retry
                        logger.warning(f"Fetch {url} -> unexpected HTTP {status}")
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempts >= max_attempts:
                    logger.error(f"Failed to fetch {url} after {attempts} attempts: {e}")
                    return None
                # jittered exponential backoff
                sleep_s = base * (2 ** (attempts - 1)) + random.uniform(0, 0.4)
                await asyncio.sleep(sleep_s)
            except Exception as e:
                logger.exception(f"Unexpected exception fetching {url}: {e}")
                return None

        return None

    async def close(self):
        """
        Closes the HTTP client session.
        """
        if self.session is not None:
            try:
                await self.session.close()
            except Exception:
                logger.exception("Error while closing HTTP session")
            finally:
                self.session = None
                self._limiter = None
