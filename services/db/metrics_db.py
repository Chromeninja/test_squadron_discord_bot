"""
Metrics Database Module

Provides a separate SQLite database for storing metrics data (voice sessions,
game activity, message counts). Isolated from the main bot database to avoid
write contention from high-frequency metric inserts.
"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager

import aiosqlite

from utils.logging import get_logger

logger = get_logger(__name__)


class MetricsDatabase:
    """
    Manages a separate SQLite database exclusively for metrics data.

    Uses WAL mode and busy_timeout for concurrent read/write safety.
    Schema is initialized via init_metrics_schema().
    """

    _db_path: str | None = None
    _initialized: bool = False

    @classmethod
    async def initialize(cls, db_path: str | None = None) -> None:
        """
        Initialize the metrics database.

        Args:
            db_path: Path to the metrics SQLite file. Defaults to 'metrics.db'.
        """
        if cls._initialized:
            return

        cls._db_path = db_path or "metrics.db"
        logger.info("Initializing metrics database at %s", cls._db_path)

        async with cls.get_connection() as db:
            await init_metrics_schema(db)

        cls._initialized = True
        logger.info("Metrics database initialized successfully")

    @classmethod
    @asynccontextmanager
    async def get_connection(cls):
        """
        Get a connection to the metrics database with optimized settings.

        Usage:
            async with MetricsDatabase.get_connection() as db:
                await db.execute("SELECT * FROM voice_sessions")
        """
        if not cls._db_path:
            raise RuntimeError(
                "MetricsDatabase not initialized — call initialize() first"
            )

        async with aiosqlite.connect(cls._db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA foreign_keys=ON")
            try:
                await db.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc).lower():
                    await asyncio.sleep(0.05)
                    await db.execute("PRAGMA journal_mode=WAL")
                else:
                    raise
            await db.execute("PRAGMA synchronous=NORMAL")
            db.row_factory = aiosqlite.Row
            yield db

    @classmethod
    def reset(cls) -> None:
        """Reset initialization state (for testing)."""
        cls._db_path = None
        cls._initialized = False


async def init_metrics_schema(db: aiosqlite.Connection) -> None:
    """
    Initialize the metrics database schema.

    Creates all metrics-specific tables with appropriate indexes.
    All timestamps are Unix epoch seconds (INTEGER).

    Args:
        db: An open aiosqlite connection to the metrics database.
    """
    await db.execute("PRAGMA foreign_keys=ON")

    # Schema version tracking
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER DEFAULT (strftime('%s','now'))
        )
        """
    )
    await db.execute(
        """
        INSERT OR IGNORE INTO metrics_schema_migrations (version, applied_at)
        VALUES (1, strftime('%s','now'))
        """
    )

    # -----------------------------------------------------------------------
    # Voice Sessions — raw session log
    # Records each voice channel join/leave as a discrete session.
    # -----------------------------------------------------------------------
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            joined_at INTEGER NOT NULL,
            left_at INTEGER,
            duration_seconds INTEGER
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_user "
        "ON voice_sessions(guild_id, user_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_joined "
        "ON voice_sessions(guild_id, joined_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_sessions_open "
        "ON voice_sessions(left_at) WHERE left_at IS NULL"
    )

    # -----------------------------------------------------------------------
    # Game Sessions — raw activity/presence log
    # Records each game play session start/stop.
    # -----------------------------------------------------------------------
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            ended_at INTEGER,
            duration_seconds INTEGER
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_sessions_guild_user "
        "ON game_sessions(guild_id, user_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_sessions_guild_started "
        "ON game_sessions(guild_id, started_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_sessions_game "
        "ON game_sessions(guild_id, game_name)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_sessions_open "
        "ON game_sessions(ended_at) WHERE ended_at IS NULL"
    )

    # -----------------------------------------------------------------------
    # Message Counts — message-window bucketed counters
    # Upserted on each message event; one row per user per bucket.
    #
    # `hour_bucket` is retained as a legacy column name for compatibility,
    # but now stores 3-minute window buckets for new writes.
    # `bucket_seconds` tags bucket granularity so cadence queries can ignore
    # legacy hourly rows (3600) and only use 3-minute rows (180).
    # -----------------------------------------------------------------------
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS message_counts (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            hour_bucket INTEGER NOT NULL,
            bucket_seconds INTEGER NOT NULL DEFAULT 3600,
            message_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, hour_bucket)
        )
        """
    )
    # Migrate existing DBs created before bucket_seconds existed.
    cursor = await db.execute("PRAGMA table_info(message_counts)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "bucket_seconds" not in columns:
        await db.execute(
            "ALTER TABLE message_counts "
            "ADD COLUMN bucket_seconds INTEGER NOT NULL DEFAULT 3600"
        )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_message_counts_guild_hour "
        "ON message_counts(guild_id, hour_bucket)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_message_counts_guild_bucket_seconds "
        "ON message_counts(guild_id, bucket_seconds, hour_bucket)"
    )

    # -----------------------------------------------------------------------
    # Metrics Hourly — pre-aggregated server-wide rollups
    # One row per guild per hour with aggregate totals.
    # -----------------------------------------------------------------------
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_hourly (
            guild_id INTEGER NOT NULL,
            hour_bucket INTEGER NOT NULL,
            total_messages INTEGER NOT NULL DEFAULT 0,
            unique_messagers INTEGER NOT NULL DEFAULT 0,
            total_voice_seconds INTEGER NOT NULL DEFAULT 0,
            unique_voice_users INTEGER NOT NULL DEFAULT 0,
            top_game TEXT,
            PRIMARY KEY (guild_id, hour_bucket)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_hourly_guild_hour "
        "ON metrics_hourly(guild_id, hour_bucket)"
    )

    # -----------------------------------------------------------------------
    # Metrics User Hourly — pre-aggregated per-user rollups
    # One row per user per guild per hour.
    # -----------------------------------------------------------------------
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_user_hourly (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            hour_bucket INTEGER NOT NULL,
            messages_sent INTEGER NOT NULL DEFAULT 0,
            voice_seconds INTEGER NOT NULL DEFAULT 0,
            games_json TEXT,
            PRIMARY KEY (guild_id, user_id, hour_bucket)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_user_hourly_guild_hour "
        "ON metrics_user_hourly(guild_id, hour_bucket)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_user_hourly_user "
        "ON metrics_user_hourly(guild_id, user_id, hour_bucket)"
    )

    await db.commit()
    logger.info("Metrics schema initialization complete")
