# helpers/http_helper.py

import aiohttp
from typing import Optional
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

class HTTPClient:
    """
    HTTP client for making asynchronous HTTP requests with a single ClientSession.
    """

    def __init__(self):
        self.session = None

    async def init_session(self):
        """
        Initializes the ClientSession.
        """
        if self.session is None:
            connector = aiohttp.TCPConnector(limit_per_host=10)
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def fetch_html(self, url: str) -> Optional[str]:
        """
        Fetches HTML content from a given URL asynchronously.

        Args:
            url (str): The URL to fetch HTML content from.

        Returns:
            Optional[str]: The fetched HTML content as a string, or None if failed.
        """
        if self.session is None:
            logger.error("HTTPClient session not initialized.")
            return None
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                return await response.text()
        except Exception as e:
            logger.exception(f"Exception occurred while fetching {url}: {e}")
            return None

    async def close(self):
        """
        Closes the HTTP client session.
        """
        if self.session is not None:
            await self.session.close()
            self.session = None
