"""
HTTP client utilities with retry support and observability.

Provides a robust HTTP client wrapper with:
- Configurable timeouts and concurrency
- Retry with exponential backoff for transient failures
- Clear error taxonomy (NotFoundError, ForbiddenError, RetryableError)
- Session lifecycle management
- Structured logging for all operations
"""

import asyncio
import os
import random
from dataclasses import dataclass

import aiohttp

from utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Error Taxonomy
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when a 404 is encountered and the caller should treat the resource as gone."""


class ForbiddenError(Exception):
    """Raised when a 403 is encountered (access denied, possible rate limiting)."""


class RetryableError(Exception):
    """Raised for transient errors that may succeed on retry."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class PermanentError(Exception):
    """Raised for errors that should not be retried."""


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------

@dataclass
class HTTPRetryPolicy:
    """Configuration for HTTP retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    # Status codes that trigger retry
    retryable_statuses: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
    # Methods that are safe to retry
    retryable_methods: frozenset[str] = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add ±25% jitter to prevent thundering herd
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0.1, delay)

    def should_retry(self, status: int, method: str) -> bool:
        """Determine if a request should be retried based on status and method."""
        return status in self.retryable_statuses and method.upper() in self.retryable_methods


# Default policies
DEFAULT_RETRY_POLICY = HTTPRetryPolicy()
NO_RETRY_POLICY = HTTPRetryPolicy(max_attempts=1)


class HTTPClient:
    """
    HTTP client with retry support and observability.

    Features:
    - Configurable timeouts and concurrency
    - Optional retry with exponential backoff
    - Structured logging for all requests
    - Clean session lifecycle management
    """

    def __init__(
        self,
        timeout: int = 15,
        concurrency: int = 8,
        user_agent: str | None = None,
        retry_policy: HTTPRetryPolicy | None = None,
    ) -> None:
        """
        Initialize HTTP client.

        Args:
            timeout: Total request timeout seconds.
            concurrency: Max in-flight requests.
            user_agent: Optional UA string. If not provided a conservative default is used.
            retry_policy: Retry configuration. If None, uses default policy.
                         Set to NO_RETRY_POLICY to disable retries.
        """
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._sem = asyncio.Semaphore(concurrency)
        self._session: aiohttp.ClientSession | None = None
        self._user_agent = user_agent or "Mozilla/5.0 TESTBot"

        # Retry configuration (can be overridden via env)
        if retry_policy is None:
            retry_enabled = os.environ.get("HTTP_RETRY_ENABLED", "true").lower() == "true"
            if retry_enabled:
                self._retry_policy = DEFAULT_RETRY_POLICY
            else:
                self._retry_policy = NO_RETRY_POLICY
        else:
            self._retry_policy = retry_policy

        # Track session status for health checks
        self._request_count = 0
        self._error_count = 0
        self._retry_count = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout, raise_for_status=False
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session cleanly."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("HTTP session closed")

    def get_health_status(self) -> dict:
        """Return health metrics for observability endpoints."""
        return {
            "http_client_status": "ok" if self._session and not self._session.closed else "closed",
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "total_retries": self._retry_count,
            "retry_enabled": self._retry_policy.max_attempts > 1,
        }

    async def fetch_html(
        self,
        url: str,
        *,
        method: str = "GET",
        retry: bool = True,
    ) -> str | None:
        """
        Fetch HTML content with optional retry support.

        Args:
            url: URL to fetch.
            method: HTTP method (default GET).
            retry: Whether to use retry policy (default True).

        Returns:
            Response text on success, None on transient failure.

        Raises:
            NotFoundError: On 404 (permanent, resource gone).
            ForbiddenError: On 403 (access denied).

        Observability:
            - Logs DEBUG on request start/completion
            - Logs WARNING on retryable failures
            - Logs INFO on retry attempts
        """
        policy = self._retry_policy if retry else NO_RETRY_POLICY
        last_error: Exception | None = None

        for attempt in range(policy.max_attempts):
            self._request_count += 1

            async with self._sem:
                # Add delay between requests to avoid bot detection
                await asyncio.sleep(0.5)

                session = await self._get_session()
                try:
                    logger.debug(f"HTTP {method} {url} (attempt {attempt + 1}/{policy.max_attempts})")

                    async with session.get(
                        url, headers={"User-Agent": self._user_agent}
                    ) as resp:
                        status = resp.status

                        if status == 200:
                            text = await resp.text()
                            logger.debug(f"HTTP {method} {url} completed ({len(text)} bytes)")
                            return text

                        if status == 404:
                            logger.warning(f"HTTP {method} {url} -> 404 (not found)")
                            raise NotFoundError(f"Resource not found: {url}")

                        if status == 403:
                            logger.warning(f"HTTP {method} {url} -> 403 (forbidden)")
                            self._error_count += 1
                            raise ForbiddenError(f"Access forbidden: {url}")

                        # Check if retryable
                        if policy.should_retry(status, method) and attempt < policy.max_attempts - 1:
                            delay = policy.calculate_delay(attempt)

                            # Handle Retry-After header for 429
                            if status == 429:
                                retry_after = resp.headers.get("Retry-After")
                                if retry_after:
                                    try:
                                        delay = min(float(retry_after), 60.0)  # Cap at 60s
                                    except ValueError:
                                        pass
                                logger.info(f"HTTP {method} {url} rate limited; waiting {delay:.1f}s")
                            else:
                                logger.info(
                                    f"HTTP {method} {url} failed ({status}); "
                                    f"retrying in {delay:.1f}s (attempt {attempt + 1}/{policy.max_attempts})"
                                )

                            self._retry_count += 1
                            await asyncio.sleep(delay)
                            continue

                        # Non-retryable error
                        logger.warning(f"HTTP {status} for {url}")
                        self._error_count += 1
                        return None

                except NotFoundError:
                    raise
                except ForbiddenError:
                    raise
                except TimeoutError as e:
                    last_error = e
                    self._error_count += 1
                    if attempt < policy.max_attempts - 1:
                        delay = policy.calculate_delay(attempt)
                        logger.info(f"Timeout for {url}; retrying in {delay:.1f}s")
                        self._retry_count += 1
                        await asyncio.sleep(delay)
                        continue
                    logger.warning(f"Timeout while fetching {url} (exhausted retries)")
                    return None
                except aiohttp.ClientError as e:
                    last_error = e
                    self._error_count += 1
                    if attempt < policy.max_attempts - 1:
                        delay = policy.calculate_delay(attempt)
                        logger.info(f"Client error for {url}: {e}; retrying in {delay:.1f}s")
                        self._retry_count += 1
                        await asyncio.sleep(delay)
                        continue
                    logger.warning(f"Client error while fetching {url}: {e}")
                    return None

        # All retries exhausted
        if last_error:
            logger.warning(f"All {policy.max_attempts} attempts failed for {url}")
        return None
