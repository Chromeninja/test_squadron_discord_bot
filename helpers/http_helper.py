# helpers/http_helper.py

import aiohttp
import logging
from typing import Optional

async def fetch_html(url: str) -> Optional[str]:
    """
    Fetches HTML content from a given URL asynchronously.

    Args:
        url (str): The URL to fetch HTML content from.

    Returns:
        Optional[str]: The fetched HTML content as a string, or None if failed.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                return await response.text()
    except Exception as e:
        logging.exception(f"Exception occurred while fetching {url}: {e}")
        return None
