# utils/tasks.py
"""
Task scheduling utilities.

Provides consistent task spawning patterns across the bot.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar


T = TypeVar("T")


def spawn(coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    """
    Create and return an asyncio task for the given coroutine.
    
    This is a consistent way to spawn tasks throughout the application,
    providing a single point of control for task creation and potential
    future enhancements like error handling, logging, or task tracking.
    
    Args:
        coro: The coroutine to run as a task
        
    Returns:
        The created asyncio task
        
    Example:
        task = spawn(some_async_function())
        await task
    """
    return asyncio.create_task(coro)
