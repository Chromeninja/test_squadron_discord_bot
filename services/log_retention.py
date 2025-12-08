"""
Optional, manual-only log retention helpers.

Provides a narrow helper to prune database-backed operational tables without
scheduling or configuration coupling. Intended for staff-triggered cleanup.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from services.db.database import Database
from utils.logging import get_logger

if TYPE_CHECKING:
    import aiosqlite

logger = get_logger(__name__)


async def prune_old_logs(
    db: aiosqlite.Connection, max_age_days: int = 30
) -> dict[str, int]:
    """Delete old admin_action_log and voice_cooldowns rows.

    Args:
        db: Open database connection.
        max_age_days: Age threshold in days for deletion.

    Returns:
        Mapping with counts of deleted rows per table.
    """
    if max_age_days <= 0:
        raise ValueError("max_age_days must be positive")

    cutoff_ts = int(time.time()) - (max_age_days * 86400)

    cursor = await db.execute(
        "DELETE FROM admin_action_log WHERE timestamp < ?", (cutoff_ts,)
    )
    admin_deleted = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

    cursor = await db.execute(
        "DELETE FROM voice_cooldowns WHERE timestamp < ?", (cutoff_ts,)
    )
    voice_deleted = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

    await db.commit()

    logger.info(
        "Pruned old log tables",
        extra={
            "max_age_days": max_age_days,
            "admin_action_log_deleted": admin_deleted,
            "voice_cooldowns_deleted": voice_deleted,
        },
    )

    return {
        "admin_action_log_deleted": admin_deleted,
        "voice_cooldowns_deleted": voice_deleted,
    }


async def prune_old_logs_managed(max_age_days: int = 30) -> dict[str, int]:
    """Convenience wrapper that manages the database connection."""
    async with Database.get_connection() as db:
        return await prune_old_logs(db, max_age_days)
