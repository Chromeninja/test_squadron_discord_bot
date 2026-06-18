"""Migration helpers for managed_events table compatibility."""

import aiosqlite

from utils.logging import get_logger

logger = get_logger(__name__)


async def _ensure_managed_event_columns(db: aiosqlite.Connection) -> None:
    """Ensure managed event compatibility columns exist on legacy databases."""
    cursor = await db.execute("PRAGMA table_info(managed_events)")
    rows = await cursor.fetchall()
    existing_columns = {str(row[1]) for row in rows}

    if "recurrence_rule" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events ADD COLUMN recurrence_rule TEXT DEFAULT NULL"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "recurrence_rule"},
        )

    if "recurrence_rule_payload" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events "
            "ADD COLUMN recurrence_rule_payload TEXT DEFAULT NULL"
        )
        logger.info(
            "Added missing column to table",
            extra={
                "table": "managed_events",
                "column": "recurrence_rule_payload",
            },
        )

    if "channel_name" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events ADD COLUMN channel_name TEXT DEFAULT NULL"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "channel_name"},
        )

    if "image_url" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events ADD COLUMN image_url TEXT DEFAULT NULL"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "image_url"},
        )

    if "user_count_current" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events "
            "ADD COLUMN user_count_current INTEGER NOT NULL DEFAULT 0"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "user_count_current"},
        )

    if "user_count_last_synced_at" not in existing_columns:
        await db.execute(
            "ALTER TABLE managed_events "
            "ADD COLUMN user_count_last_synced_at INTEGER DEFAULT NULL"
        )
        logger.info(
            "Added missing column to table",
            extra={"table": "managed_events", "column": "user_count_last_synced_at"},
        )

    if "signup_role_ids" in existing_columns:
        await db.execute(
            """
            CREATE TABLE managed_events_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_event_id TEXT DEFAULT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT NULL,
                announcement_message TEXT DEFAULT NULL,
                scheduled_start_time TEXT NOT NULL,
                scheduled_end_time TEXT DEFAULT NULL,
                entity_type TEXT NOT NULL DEFAULT 'voice',
                channel_id TEXT DEFAULT NULL,
                channel_name TEXT DEFAULT NULL,
                location TEXT DEFAULT NULL,
                image_url TEXT DEFAULT NULL,
                announcement_channel_id TEXT DEFAULT NULL,
                announcement_message_id TEXT DEFAULT NULL,
                signup_message_id TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                revision INTEGER NOT NULL DEFAULT 1,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                sync_error TEXT DEFAULT NULL,
                user_count_current INTEGER NOT NULL DEFAULT 0,
                user_count_last_synced_at INTEGER DEFAULT NULL,
                last_synced_at INTEGER DEFAULT NULL,
                last_projected_hash TEXT DEFAULT NULL,
                source TEXT NOT NULL DEFAULT 'dashboard',
                created_by_user_id TEXT DEFAULT NULL,
                created_by_name TEXT DEFAULT NULL,
                updated_by_user_id TEXT DEFAULT NULL,
                updated_by_name TEXT DEFAULT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                deleted_at INTEGER DEFAULT NULL,
                recurrence_rule TEXT DEFAULT NULL,
                recurrence_rule_payload TEXT DEFAULT NULL
            )
            """
        )
        await db.execute(
            """
            INSERT INTO managed_events_v2 (
                id,
                guild_id,
                discord_event_id,
                name,
                description,
                announcement_message,
                scheduled_start_time,
                scheduled_end_time,
                entity_type,
                channel_id,
                channel_name,
                location,
                image_url,
                announcement_channel_id,
                announcement_message_id,
                signup_message_id,
                status,
                revision,
                sync_status,
                sync_error,
                user_count_current,
                user_count_last_synced_at,
                last_synced_at,
                last_projected_hash,
                source,
                created_by_user_id,
                created_by_name,
                updated_by_user_id,
                updated_by_name,
                created_at,
                updated_at,
                deleted_at,
                recurrence_rule,
                recurrence_rule_payload
            )
            SELECT
                id,
                guild_id,
                discord_event_id,
                name,
                description,
                announcement_message,
                scheduled_start_time,
                scheduled_end_time,
                entity_type,
                channel_id,
                channel_name,
                location,
                image_url,
                announcement_channel_id,
                announcement_message_id,
                signup_message_id,
                status,
                revision,
                sync_status,
                sync_error,
                user_count_current,
                user_count_last_synced_at,
                last_synced_at,
                last_projected_hash,
                source,
                created_by_user_id,
                created_by_name,
                updated_by_user_id,
                updated_by_name,
                created_at,
                updated_at,
                deleted_at,
                recurrence_rule,
                recurrence_rule_payload
            FROM managed_events
            """
        )
        await db.execute("DROP TABLE managed_events")
        await db.execute("ALTER TABLE managed_events_v2 RENAME TO managed_events")
        logger.info(
            "Removed deprecated column from table",
            extra={"table": "managed_events", "column": "signup_role_ids"},
        )

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_managed_events_guild ON managed_events(guild_id, deleted_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_managed_events_sync ON managed_events(guild_id, sync_status, updated_at)"
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_managed_events_guild_discord ON managed_events(guild_id, discord_event_id)"
    )
