"""Migration helpers for event signup feature columns."""

import aiosqlite

from utils.logging import get_logger

logger = get_logger(__name__)


async def _ensure_event_signup_columns(db: aiosqlite.Connection) -> None:
    """Ensure managed_events has event-level signup setting columns."""
    cursor = await db.execute("PRAGMA table_info(managed_events)")
    rows = await cursor.fetchall()
    existing_columns = {str(row[1]) for row in rows}

    if "signups_enabled" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events "
            "ADD COLUMN signups_enabled INTEGER NOT NULL DEFAULT 1"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "signups_enabled"},
        )

    if "signups_closed" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events "
            "ADD COLUMN signups_closed INTEGER NOT NULL DEFAULT 0"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "signups_closed"},
        )

    if "allow_multiple_roles" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events "
            "ADD COLUMN allow_multiple_roles INTEGER NOT NULL DEFAULT 0"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "allow_multiple_roles"},
        )

    if "signup_channel_id" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events ADD COLUMN signup_channel_id TEXT DEFAULT NULL"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "signup_channel_id"},
        )
