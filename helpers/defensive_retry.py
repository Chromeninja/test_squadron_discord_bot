#helpers/defensive_retry.py

"""
Robust retry mechanisms with exponential backoff for external API calls.

This module provides defensive retry patterns specifically designed for AI agent
robustness when dealing with external services and Discord API calls.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import aiohttp
import discord

logger = logging.getLogger(__name__)

T = TypeVar("T")

class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add ±25% jitter to prevent thundering herd
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

# Predefined retry configurations for different use cases
RETRY_CONFIGS = {
    "discord_api": RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=16.0,
        exponential_base=2.0,
        jitter=True
    ),
    "external_api": RetryConfig(
        max_attempts=5,
        base_delay=2.0,
        max_delay=120.0,
        exponential_base=2.0,
        jitter=True
    ),
    "database": RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=8.0,
        exponential_base=2.0,
        jitter=True
    ),
    "quick": RetryConfig(
        max_attempts=2,
        base_delay=0.1,
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False
    )
}

def is_retryable_error(error: Exception) -> bool:
    """Determine if an error is worth retrying."""

    # Discord API errors that are retryable
    if isinstance(error, discord.HTTPException):
        # Rate limited - definitely retry
        if error.status == 429:
            return True
        # Server errors - retry
        if 500 <= error.status < 600:
            return True
        # Gateway timeout - retry
        if error.status == 504:
            return True
        # Client errors - usually don't retry
        if 400 <= error.status < 500:
            return False

    # Network errors - retry
    if isinstance(error, aiohttp.ClientError | asyncio.TimeoutError):
        return True

    # Connection errors - retry
    if isinstance(error, ConnectionError | OSError):
        return True

    # Unknown errors - be conservative, don't retry
    return False

async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    config: RetryConfig | None = None,
    config_name: str = "discord_api",
    **kwargs: Any
) -> T:
    """
    Retry an async function with exponential backoff.

    Args:
        func: The async function to retry
        *args: Arguments to pass to func
        config: Custom retry configuration
        config_name: Name of predefined config to use if config is None
        **kwargs: Keyword arguments to pass to func

    Returns:
        The result of the successful function call

    Raises:
        The last exception if all retries are exhausted
    """
    if config is None:
        config = RETRY_CONFIGS.get(config_name, RETRY_CONFIGS["discord_api"])

    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(
                    f"Function {func.__name__} succeeded on attempt {attempt + 1}"
                )
            return result

        except Exception as e:
            last_exception = e

            # Log the attempt
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed for "
                f"{func.__name__}: {type(e).__name__}: {e}"
            )

            # Check if we should retry
            if not is_retryable_error(e):
                logger.exception(
                    f"Non-retryable error for {func.__name__}: {type(e).__name__}: {e}"
                )
                raise

            # Don't delay on the last attempt
            if attempt < config.max_attempts - 1:
                delay = config.calculate_delay(attempt)
                logger.info(f"Retrying {func.__name__} in {delay:.2f}s...")
                await asyncio.sleep(delay)

    # All retries exhausted
    logger.error(
        f"All {config.max_attempts} attempts failed for {func.__name__}: "
        f"{type(last_exception).__name__}: {last_exception}"
    )
    raise last_exception

def retry_decorator(
    config: RetryConfig | None = None,
    config_name: str = "discord_api"
):
    """
    Decorator to add retry logic to async functions.

    Example:
        @retry_decorator(config_name='external_api')
        async def fetch_rsi_profile(handle: str) -> dict:
            # Function that might fail
            pass
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_async(
                func, *args, config=config, config_name=config_name, **kwargs
            )
        return wrapper
    return decorator

# Convenience decorators for common cases
discord_retry = retry_decorator(config_name="discord_api")
external_api_retry = retry_decorator(config_name="external_api")
database_retry = retry_decorator(config_name="database")
quick_retry = retry_decorator(config_name="quick")

# Context manager for batch operations with circuit breaker
class CircuitBreaker:
    """Simple circuit breaker to prevent cascade failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed, open, half_open

    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking calls)."""
        if self.state == "open":
            if asyncio.get_event_loop().time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
                logger.info("Circuit breaker moving to half-open state")
                return False
            return True
        return False

    def record_success(self) -> None:
        """Record a successful operation."""
        if self.state == "half_open":
            self.state = "closed"
            self.failure_count = 0
            logger.info("Circuit breaker closed after successful recovery")

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )

# Global circuit breakers for different services
CIRCUIT_BREAKERS = {
    "rsi_api": CircuitBreaker(failure_threshold=10, recovery_timeout=300.0),
    "discord_api": CircuitBreaker(failure_threshold=20, recovery_timeout=60.0),
    "database": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
}

async def with_circuit_breaker(
    func: Callable[..., Awaitable[T]],
    circuit_name: str,
    *args: Any,
    **kwargs: Any
) -> T:
    """Execute function with circuit breaker protection."""
    circuit = CIRCUIT_BREAKERS.get(circuit_name)
    if not circuit:
        # No circuit breaker configured, execute directly
        return await func(*args, **kwargs)

    if circuit.is_open():
        raise Exception(f"Circuit breaker {circuit_name} is open")

    try:
        result = await func(*args, **kwargs)
        circuit.record_success()
        return result
    except Exception:
        circuit.record_failure()
        raise
