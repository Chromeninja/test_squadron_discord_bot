# helpers/retry.py

import asyncio
import random
from typing import Callable, Any, TypeVar, Optional, Tuple, Type
import discord
from helpers.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 10.0,
        jitter_factor: float = 0.1,
        backoff_multiplier: float = 2.0
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.backoff_multiplier = backoff_multiplier


def should_retry_exception(exception: Exception) -> bool:
    """
    Determine if an exception should trigger a retry.
    
    Args:
        exception: The exception to check
        
    Returns:
        True if the exception should be retried, False otherwise
    """
    # Don't retry permission or not found errors
    if isinstance(exception, (discord.Forbidden, discord.NotFound)):
        return False
    
    # Retry server errors and rate limits
    if isinstance(exception, discord.DiscordServerError):
        return True
    
    # Retry HTTP exceptions with 5xx status codes
    if isinstance(exception, discord.HTTPException):
        status = getattr(exception, "status", None)
        if isinstance(status, int) and 500 <= status < 600:
            return True
        # Also retry on rate limits (429)
        if isinstance(status, int) and status == 429:
            return True
    
    # Retry on connection errors and timeouts
    if isinstance(exception, (asyncio.TimeoutError, ConnectionError)):
        return True
    
    return False


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate the delay for a retry attempt with exponential backoff and jitter.
    
    Args:
        attempt: The current attempt number (1-based)
        config: Retry configuration
        
    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * (multiplier ^ (attempt - 1))
    delay = config.base_delay * (config.backoff_multiplier ** (attempt - 1))
    
    # Cap at max_delay
    delay = min(delay, config.max_delay)
    
    # Add jitter to avoid thundering herd
    jitter = random.uniform(0, config.jitter_factor * delay)
    delay += jitter
    
    return delay


async def retry_async(
    func: Callable[..., Any],
    *args,
    config: Optional[RetryConfig] = None,
    operation_name: str = "operation",
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff and jitter.
    
    Args:
        func: The async function to retry
        *args: Positional arguments to pass to func
        config: Retry configuration (uses default if None)
        operation_name: Name of the operation for logging
        **kwargs: Keyword arguments to pass to func
        
    Returns:
        The result of the successful function call
        
    Raises:
        The last exception if all retries are exhausted
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            # Check if we should retry this exception
            if not should_retry_exception(e):
                logger.error(f"{operation_name} failed with non-retryable error: {e}")
                raise e
            
            # Don't retry if this is the last attempt
            if attempt >= config.max_attempts:
                logger.error(f"{operation_name} failed after {config.max_attempts} attempts: {e}")
                break
            
            # Calculate delay and log retry
            delay = calculate_delay(attempt, config)
            logger.warning(
                f"{operation_name} failed (attempt {attempt}/{config.max_attempts}), "
                f"retrying in {delay:.2f}s: {e}"
            )
            
            # Wait before retry
            await asyncio.sleep(delay)
    
    # If we get here, all retries were exhausted
    if last_exception:
        raise last_exception
    else:
        raise RuntimeError(f"{operation_name} failed with no exception recorded")


def with_retry(
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None
):
    """
    Decorator to add retry logic to an async function.
    
    Args:
        config: Retry configuration (uses default if None)
        operation_name: Name of the operation for logging (uses function name if None)
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args, **kwargs):
            nonlocal operation_name
            if operation_name is None:
                operation_name = func.__name__
            
            return await retry_async(
                func,
                *args,
                config=config,
                operation_name=operation_name,
                **kwargs
            )
        
        return wrapper
    return decorator


__all__ = [
    'RetryConfig',
    'should_retry_exception',
    'calculate_delay', 
    'retry_async',
    'with_retry'
]
