"""
Utility functions for RSI (Roberts Space Industries) API integration.

Handles organization validation by fetching and parsing org pages.
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import aiohttp
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from bs4 import Tag

logger = logging.getLogger(__name__)

# HTTP status codes
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_TIMEOUT = 408
HTTP_SERVER_ERROR = 500


class RSIRateLimiter:
    """Rate limiter for RSI API requests."""

    def __init__(self, requests_per_minute: int = 30):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum number of requests allowed per minute
        """
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                await asyncio.sleep(wait_time)
            self.last_request_time = asyncio.get_event_loop().time()


class RSIClient:
    """Client for making requests to RSI website with rate limiting."""

    def __init__(self, requests_per_minute: int = 30, user_agent: str | None = None):
        """
        Initialize RSI client.

        Args:
            requests_per_minute: Rate limit for requests
            user_agent: User agent string for requests
        """
        self.rate_limiter = RSIRateLimiter(requests_per_minute)
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; TESTBot/1.0)"
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                raise_for_status=False
            )
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_html(self, url: str) -> tuple[str | None, int]:
        """
        Fetch HTML from URL with rate limiting.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html_content, status_code)
            html_content is None if request failed
        """
        await self.rate_limiter.acquire()

        session = await self._get_session()
        try:
            async with session.get(
                url,
                headers={"User-Agent": self.user_agent}
            ) as resp:
                status = resp.status
                if status == HTTP_OK:
                    text = await resp.text()
                    logger.debug(f"Successfully fetched {url} ({len(text)} bytes)")
                    return text, status
                else:
                    logger.warning(f"Failed to fetch {url}: HTTP {status}")
                    return None, status
        except TimeoutError:
            logger.warning(f"Timeout while fetching {url}")
            return None, HTTP_TIMEOUT
        except aiohttp.ClientError as e:
            logger.warning(f"Client error while fetching {url}: {e}")
            return None, HTTP_SERVER_ERROR
        except Exception:
            logger.exception(f"Unexpected error while fetching {url}")
            return None, HTTP_SERVER_ERROR


async def validate_organization_sid(
    sid: str,
    rsi_client: RSIClient
) -> tuple[bool, str | None, str | None]:
    """
    Validate an organization SID by fetching its page from RSI.

    Args:
        sid: Organization SID (Spectrum ID) to validate
        rsi_client: RSI client instance for making requests

    Returns:
        Tuple of (is_valid, org_name, error_message)
        - is_valid: True if org exists and was parsed successfully
        - org_name: Full organization name if found, None otherwise
        - error_message: Error description if validation failed, None otherwise
    """
    # Normalize SID to uppercase
    sid = sid.strip().upper()

    if not sid:
        return False, None, "Organization SID cannot be empty"

    # Basic validation - SID should be alphanumeric and reasonable length
    if not re.match(r'^[A-Z0-9]{1,20}$', sid):
        return (
            False,
            None,
            "Organization SID must be alphanumeric (1-20 characters)"
        )

    # Construct org page URL
    url = f"https://robertsspaceindustries.com/en/orgs/{sid}"
    logger.info(f"Validating organization SID: {sid} at {url}")

    # Fetch the page
    html, status = await rsi_client.fetch_html(url)

    # Check status codes and return appropriate error messages
    if status == HTTP_NOT_FOUND:
        return (
            False,
            None,
            f"Organization '{sid}' not found on RSI. "
            "Please verify the SID is correct."
        )

    if status == HTTP_FORBIDDEN:
        return (
            False,
            None,
            "Access forbidden by RSI. This may be due to rate limiting "
            "or bot detection. Please try again in a few minutes."
        )

    if status != HTTP_OK or html is None:
        return (
            False,
            None,
            f"Failed to fetch organization page from RSI (HTTP {status}). "
            "Please try again later."
        )

    # Parse the HTML to extract org name
    return _parse_org_name_from_html(html, sid)


def _parse_org_name_from_html(
    html: str,
    sid: str
) -> tuple[bool, str | None, str | None]:
    """
    Parse organization name from RSI org page HTML.

    Args:
        html: HTML content of org page
        sid: Organization SID for logging

    Returns:
        Tuple of (is_valid, org_name, error_message)
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Look for the org name in
        # <h1>Org Name / <span class="symbol">SID</span></h1>
        h1_tag = soup.find('h1')
        if not h1_tag:
            logger.warning(f"Could not find <h1> tag in org page for {sid}")
            return (
                False,
                None,
                "Failed to parse organization page. "
                "The page structure may have changed."
            )

        # Extract org name using different strategies
        org_name = _extract_org_name(h1_tag)

        if not org_name:
            logger.warning(
                f"Could not extract organization name from h1 for {sid}"
            )
            return False, None, "Failed to extract organization name from page."

        logger.info(f"Successfully validated organization: {org_name} ({sid})")
        return True, org_name, None

    except Exception as e:
        logger.exception(f"Error parsing organization page for {sid}")
        return False, None, f"Failed to parse organization page: {e!s}"


def _extract_org_name(h1_tag: "Tag") -> str:
    """
    Extract organization name from h1 tag.

    Args:
        h1_tag: BeautifulSoup h1 tag element

    Returns:
        Extracted organization name or empty string if not found
    """
    # Extract text from h1, excluding the symbol span
    h1_text = h1_tag.get_text(separator=' ', strip=True)

    # The format is typically: "Org Name / SID"
    # We need to extract just the org name part
    if ' / ' in h1_text:
        return h1_text.split(' / ')[0].strip()

    # Fallback: try to find the symbol span and get text before it
    symbol_span = h1_tag.find('span', class_='symbol')
    if symbol_span:
        # Get all text nodes before the span
        org_name_parts = []
        for content in h1_tag.contents:
            if content == symbol_span:
                break
            if isinstance(content, str):
                org_name_parts.append(content)
        return ''.join(org_name_parts).strip().rstrip('/')

    return h1_text.strip()
