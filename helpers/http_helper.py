# helpers/http_helper.py

import aiohttp
import logging
from typing import Optional


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
            self.session = aiohttp.ClientSession()

    async def fetch_html(self, url: str) -> Optional[str]:
        """
        Fetches HTML content from a given URL asynchronously.

        Args:
            url (str): The URL to fetch HTML content from.

        Returns:
            Optional[str]: The fetched HTML content as a string, or None if failed.
        """
        if self.session is None:
            logging.error("HTTPClient session not initialized.")
            return None
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                return await response.text()
        except Exception as e:
            logging.exception(f"Exception occurred while fetching {url}: {e}")
            return None

    async def close(self):
        """
        Closes the HTTP client session.
        """
        if self.session is not None:
            await self.session.close()
