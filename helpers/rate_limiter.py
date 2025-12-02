import time

from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)

# Default rate limit configuration (used when guild context not available)
DEFAULT_RATE_LIMITS = {
    "verification": {"max_attempts": 5, "window_seconds": 1800},
    "recheck": {"max_attempts": 1, "window_seconds": 300},
}


async def _get_limits(guild_config, guild_id: int, action: str) -> tuple[int, int]:
    """
    Get rate limit configuration for a specific guild and action.

    Args:
        guild_config: GuildConfigHelper instance
        guild_id: Discord guild ID
        action: Rate limit action type ("verification" or "recheck")

    Returns:
        Tuple of (max_attempts, window_seconds)
    """
    if action == "recheck":
        max_attempts = await guild_config.get_setting(
            guild_id, "rate_limits.recheck_max_attempts", default=1, parser=int
        )
        window = await guild_config.get_setting(
            guild_id, "rate_limits.recheck_window_seconds", default=300, parser=int
        )
        return max_attempts, window

    max_attempts = await guild_config.get_setting(
        guild_id, "rate_limits.max_attempts", default=5, parser=int
    )
    window = await guild_config.get_setting(
        guild_id, "rate_limits.window_seconds", default=1800, parser=int
    )
    return max_attempts, window


def _get_default_limits(action: str) -> tuple[int, int]:
    """Get default limits when guild context unavailable."""
    config = DEFAULT_RATE_LIMITS.get(action, DEFAULT_RATE_LIMITS["verification"])
    return config["max_attempts"], config["window_seconds"]


async def check_rate_limit(
    user_id_or_guild_config,
    action_or_guild_id: str | int = "verification",
    user_id: int | None = None,
    action: str | None = None,
) -> tuple[bool, int]:
    """
    Check if user has hit rate limit. Supports both old and new call patterns.

    Old pattern: check_rate_limit(user_id, "verification")
    New pattern: check_rate_limit(guild_config, guild_id, user_id, "verification")
    """
    # Detect call pattern
    if isinstance(user_id_or_guild_config, int):
        # Old pattern: check_rate_limit(user_id, action)
        user_id_val = user_id_or_guild_config
        action_val = (
            action_or_guild_id
            if isinstance(action_or_guild_id, str)
            else "verification"
        )
        max_attempts, window = _get_default_limits(action_val)
    else:
        # New pattern: check_rate_limit(guild_config, guild_id, user_id, action)
        guild_config = user_id_or_guild_config
        guild_id = action_or_guild_id  # type: ignore
        user_id_val = user_id  # type: ignore
        action_val = action or "verification"
        max_attempts, window = await _get_limits(guild_config, guild_id, action_val)

    row = await Database.fetch_rate_limit(user_id_val, action_val)
    now = int(time.time())
    if row:
        attempts, first = row
        if now - first >= window:
            await Database.reset_rate_limit(user_id_val, action_val)
            return False, 0
        if attempts >= max_attempts:
            logger.info(
                "Rate limit hit.", extra={"user_id": user_id_val, "action": action_val}
            )
            return True, first + window
    return False, 0


async def log_attempt(user_id: int, action: str = "verification") -> None:
    await Database.increment_rate_limit(user_id, action)
    logger.debug("Logged attempt.", extra={"user_id": user_id, "action": action})


async def get_remaining_attempts(
    user_id_or_guild_config,
    action_or_guild_id: str | int = "verification",
    user_id: int | None = None,
    action: str | None = None,
) -> int:
    """
    Get remaining attempts for user. Supports both old and new call patterns.

    Old pattern: get_remaining_attempts(user_id, "verification")
    New pattern: get_remaining_attempts(guild_config, guild_id, user_id, "verification")
    """
    # Detect call pattern
    if isinstance(user_id_or_guild_config, int):
        # Old pattern
        user_id_val = user_id_or_guild_config
        action_val = (
            action_or_guild_id
            if isinstance(action_or_guild_id, str)
            else "verification"
        )
        max_attempts, window = _get_default_limits(action_val)
    else:
        # New pattern
        guild_config = user_id_or_guild_config
        guild_id = action_or_guild_id  # type: ignore
        user_id_val = user_id  # type: ignore
        action_val = action or "verification"
        max_attempts, window = await _get_limits(guild_config, guild_id, action_val)

    row = await Database.fetch_rate_limit(user_id_val, action_val)
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
    """
    Clean up expired rate limit entries (all guilds).

    Note: Uses default windows for cleanup. This is a background task that
    runs periodically to clean up old data across all guilds.
    """
    # Use default windows for cleanup
    _, recheck_window = _get_default_limits("recheck")
    _, verify_window = _get_default_limits("verification")

    now = int(time.time())
    try:
        async with Database.get_connection() as db:
            await db.execute(
                "DELETE FROM rate_limits WHERE action = 'recheck' AND (? - first_attempt) > ?",
                (now, recheck_window),
            )
            await db.execute(
                "DELETE FROM rate_limits WHERE action != 'recheck' AND (? - first_attempt) > ?",
                (now, verify_window),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to cleanup rate limit attempts")
    logger.debug("Cleaned up expired rate-limiting data.")


async def reset_all_attempts() -> None:
    await Database.reset_rate_limit()
    logger.info("Reset all verification attempts.")
