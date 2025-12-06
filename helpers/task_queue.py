import asyncio
import random
import time

import discord
from aiolimiter import AsyncLimiter

from utils.logging import get_logger

logger = get_logger(__name__)


task_queue = asyncio.Queue()

# Track worker tasks for clean shutdown
_worker_tasks: set[asyncio.Task] = set()

api_limiter = AsyncLimiter(max_rate=45, time_period=1)


async def worker() -> None:
    """
    Worker coroutine that processes tasks from the task_queue.
    """
    while True:
        task = await task_queue.get()
        if task is None:
            task_queue.task_done()
            logger.info("Worker received shutdown signal.")
            break  # Exit the worker
        try:
            async with api_limiter:
                await run_task(task)
        except Exception:
            logger.exception("Error running queued task")
        finally:
            task_queue.task_done()


async def run_task(task) -> None:
    """
    Executes the given task.

    Args:
        task (Callable): An asynchronous callable representing the task.
    """
    # Retry transient Discord server errors (5xx/DiscordServerError).
    MAX_RETRIES = 3
    BASE_DELAY = 0.5
    attempt = 0
    while True:
        try:
            return await task()
        except Exception as e:
            attempt += 1
            # Decide whether to retry: DiscordServerError or HTTPException with 5xx
            should_retry = False
            if isinstance(e, discord.DiscordServerError):
                should_retry = True
            elif isinstance(e, discord.HTTPException):
                # Prefer the numeric HTTP status when available to detect 5xx
                status = getattr(e, "status", None)
                if isinstance(status, int) and 500 <= status < 600:
                    should_retry = True

            # Only retry while attempt < MAX_RETRIES so the total number of
            # attempts equals MAX_RETRIES (no extra attempt beyond the limit).
            if should_retry and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1))
                # jitter
                delay = delay + random.uniform(0, 0.1 * delay)
                logger.warning(
                    f"Transient error in queued task (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.2f}s: {e}"
                )
                await asyncio.sleep(delay)
                continue

            logger.exception("Exception in task")
            return None


async def enqueue_task(task) -> None:
    """
    Enqueues a task to be processed by the worker.

    Args:
        task (Callable): An asynchronous callable representing the task.
    """
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    async def wrapped_task() -> None:
        result = await task()
        if not future.done():
            future.set_result(result)

    await task_queue.put(wrapped_task)
    logger.debug("Task enqueued.")
    return future  # type: ignore[return-value]


async def start_task_workers(num_workers=2) -> None:
    """
    Starts the specified number of worker tasks.

    Args:
        num_workers (int): Number of worker coroutines to start.
    """
    for idx in range(num_workers):
        task = asyncio.create_task(worker(), name=f"task_queue_worker_{idx}")
        _worker_tasks.add(task)

        def _cleanup(done: asyncio.Task) -> None:
            _worker_tasks.discard(done)
            try:
                exc = done.exception()
                if exc:
                    logger.exception(
                        "Task queue worker %s failed", done.get_name(), exc_info=exc
                    )
            except asyncio.CancelledError:
                logger.debug("Task queue worker %s cancelled", done.get_name())
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Error inspecting worker task %s: %s", done.get_name(), exc
                )

        task.add_done_callback(_cleanup)
    logger.info(f"Started {num_workers} task queue worker(s).")


async def stop_task_workers() -> None:
    """Signal all worker tasks to exit and await completion."""

    if not _worker_tasks:
        return

    for _ in range(len(_worker_tasks)):
        await task_queue.put(None)

    await task_queue.join()
    await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()


async def flush_tasks(max_wait: float = 2.0) -> None:
    """Best-effort wait until the task_queue is drained or timeout.

    Ensures leadership logging can observe role/nickname changes that were
    enqueued just prior. Non-blocking (uses asyncio.sleep)."""
    deadline = time.time() + max_wait
    # Initial yield to let workers pick up tasks
    await asyncio.sleep(0)
    while time.time() < deadline:
        if task_queue.empty():
            # Give in-flight task a brief chance to finish
            await asyncio.sleep(0.05)
            if task_queue.empty():
                break
        await asyncio.sleep(0.05)


__all__ = [
    "enqueue_task",
    "flush_tasks",
    "start_task_workers",
    "stop_task_workers",
    "task_queue",
]
