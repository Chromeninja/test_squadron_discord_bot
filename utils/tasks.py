"""
Task utilities for managing asyncio tasks and background operations.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """
    Spawn a coroutine as a background task.

    This is a convenience function that creates an asyncio task and logs
    any exceptions that occur during execution.

    Args:
        coro: The coroutine to spawn as a task

    Returns:
        The created asyncio task
    """
    try:
        task = asyncio.create_task(coro)
        task.add_done_callback(_log_task_exception)
        return task
    except Exception as e:
        logger.exception(f"Failed to spawn task: {e}")
        raise


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Log exceptions from completed tasks."""
    try:
        if task.exception():
            logger.exception(f"Task {task.get_name()} failed with exception", exc_info=task.exception())
    except Exception as e:
        # This shouldn't happen, but let's be safe
        logger.exception(f"Error logging task exception: {e}")


async def wait_for_any(*tasks: asyncio.Task[Any]) -> Any:
    """
    Wait for any of the given tasks to complete.

    Args:
        *tasks: Tasks to wait for

    Returns:
        The result of the first completed task
    """
    if not tasks:
        raise ValueError("No tasks provided")

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    # Cancel pending tasks
    for task in pending:
        task.cancel()

    # Return the result of the first completed task
    completed_task = next(iter(done))
    return await completed_task
