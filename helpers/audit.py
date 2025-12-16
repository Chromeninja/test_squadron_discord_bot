"""Admin action audit logging."""

import json
import time

from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)


async def log_admin_action(
    admin_user_id: int,
    guild_id: int,
    action: str,
    target_user_id: int | None = None,
    details: dict | None = None,
    status: str = "success",
) -> None:
    """
    Log an admin action to the audit table.

    Args:
        admin_user_id: Discord user ID of the admin performing the action (integer)
        guild_id: Discord guild ID where action occurred (integer)
        action: Action type (e.g., "RECHECK_USER", "RESET_USER_TIMER")
        target_user_id: Optional target user ID if action affects specific user (integer)
        details: Optional dictionary of additional details (JSON encoded)
        status: Action status ("success", "error", "rate_limited", etc.)
    """
    try:
        details_json = json.dumps(details) if details else None
        await BaseRepository.execute(
            """INSERT INTO admin_action_log
               (timestamp, admin_user_id, guild_id, action,
                target_user_id, details, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                int(time.time()),
                int(admin_user_id),
                int(guild_id),
                action,
                int(target_user_id) if target_user_id is not None else None,
                details_json,
                status,
            ),
        )
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
