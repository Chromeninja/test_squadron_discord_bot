# Helpers/rate_limiter.py

import time

from config.config_loader import ConfigLoader
from helpers.database import Database
from helpers.logger import get_logger

logger = get_logger(__name__)

config = ConfigLoader.load_config()
MAX_ATTEMPTS = config["rate_limits"]["max_attempts"]
RATE_LIMIT_WINDOW = config["rate_limits"]["window_seconds"]
RECHECK_WINDOW = config["rate_limits"].get("recheck_window_seconds", 300)


def _get_limits(action: str) -> tuple[int, int]:
    if action == "recheck":
        return 1, RECHECK_WINDOW
    return MAX_ATTEMPTS, RATE_LIMIT_WINDOW


async def check_rate_limit(
    user_id: int, action: str = "verification"
) -> tuple[bool, int]:
    max_attempts, window = _get_limits(action)
    row = await Database.fetch_rate_limit(user_id, action)
    now = int(time.time())
    if row:
        attempts, first = row
        if now - first >= window:
            await Database.reset_rate_limit(user_id, action)
            return False, 0
        if attempts >= max_attempts:
            logger.info("Rate limit hit.", extra={"user_id": user_id, "action": action})
            return True, first + window
    return False, 0


async def log_attempt(user_id: int, action: str = "verification") -> None:
    await Database.increment_rate_limit(user_id, action)
    logger.debug("Logged attempt.", extra={"user_id": user_id, "action": action})


async def get_remaining_attempts(user_id: int, action: str = "verification") -> int:
    max_attempts, window = _get_limits(action)
    row = await Database.fetch_rate_limit(user_id, action)
    now = int(time.time())
    if not row:
        return max_attempts
    attempts, first = row
    if now - first >= window:
        return max_attempts
    return max_attempts - attempts


async def reset_attempts(user_id: int) -> None:
    await Database.reset_rate_limit(user_id)
    logger.info("Rate limit reset.", extra={"user_id": user_id})


async def cleanup_attempts() -> None:
    now = int(time.time())
    try:
        async with Database.get_connection() as db:
            await db.execute(
                "DELETE FROM rate_limits WHERE action = 'recheck' AND (? - first_attempt) > ?",
                (now, RECHECK_WINDOW),
            )
            await db.execute(
                "DELETE FROM rate_limits WHERE action != 'recheck' AND (? - first_attempt) > ?",
                (now, RATE_LIMIT_WINDOW),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to cleanup rate limit attempts")
    logger.debug("Cleaned up expired rate-limiting data.")


async def reset_all_attempts() -> None:
    await Database.reset_rate_limit()
    logger.info("Reset all verification attempts.")
