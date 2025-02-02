# helpers/task_queue.py

import asyncio
import time
from helpers.logger import get_logger
from aiolimiter import AsyncLimiter

logger = get_logger(__name__)


task_queue = asyncio.Queue()

api_limiter = AsyncLimiter(max_rate=45, time_period=1)

async def worker():
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
        except Exception as e:
            logger.error(f"Error running queued task: {e}")
        finally:
            task_queue.task_done()

async def run_task(task):
    """
    Executes the given task.

    Args:
        task (Callable): An asynchronous callable representing the task.
    """
    try:
        result = await task()
        return result
    except Exception as e:
        logger.exception(f"Exception in task: {e}")
        return None

async def enqueue_task(task):
    """
    Enqueues a task to be processed by the worker.

    Args:
        task (Callable): An asynchronous callable representing the task.
    """
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    async def wrapped_task():
        result = await task()
        if not future.done():
            future.set_result(result)
        return result

    await task_queue.put(wrapped_task)
    logger.debug("Task enqueued.")
    return future

async def start_task_workers(num_workers=2):
    """
    Starts the specified number of worker tasks.

    Args:
        num_workers (int): Number of worker coroutines to start.
    """
    for _ in range(num_workers):
        asyncio.create_task(worker())
    logger.info(f"Started {num_workers} task queue worker(s).")
