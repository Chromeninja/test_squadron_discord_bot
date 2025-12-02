"""Admin action audit logging."""
import json
import time

from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)


async def log_admin_action(
    admin_user_id: str,
    guild_id: str,
    action: str,
    target_user_id: str | None = None,
    details: dict | None = None,
    status: str = "success",
) -> None:
    """
    Log an admin action to the audit table.

    Args:
        admin_user_id: Discord user ID of the admin performing the action
        guild_id: Discord guild ID where action occurred
        action: Action type (e.g., "RECHECK_USER", "RESET_USER_TIMER")
        target_user_id: Optional target user ID if action affects specific user
        details: Optional dictionary of additional details (JSON encoded)
        status: Action status ("success", "error", "rate_limited", etc.)
    """
    try:
        details_json = json.dumps(details) if details else None
        async with Database.get_connection() as db:
            await db.execute(
                """INSERT INTO admin_action_log
                   (timestamp, admin_user_id, guild_id, action,
                    target_user_id, details, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(time.time()),
                    admin_user_id,
                    guild_id,
                    action,
                    target_user_id,
                    details_json,
                    status,
                ),
            )
            await db.commit()
        logger.debug(
            f"Logged admin action: {action}",
            extra={
                "admin_user_id": admin_user_id,
                "guild_id": guild_id,
                "action": action,
                "target_user_id": target_user_id,
                "status": status,
            },
        )
    except Exception as e:
        logger.exception(
            "Failed to log admin action",
            extra={
                "action": action,
                "admin_user_id": admin_user_id,
                "guild_id": guild_id,
                "error": str(e),
            },
        )

