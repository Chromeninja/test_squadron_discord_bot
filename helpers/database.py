# Helpers/database.py

import aiosqlite
import sqlite3
import asyncio
import time
from typing import Optional
from helpers.logger import get_logger
from contextlib import asynccontextmanager

logger = get_logger(__name__)


class Database:
    _db_path: str = "TESTDatabase.db"
    _lock = asyncio.Lock()  # Ensures that only one initialization happens
    _initialized = False

    @classmethod
    async def get_auto_recheck_fail_count(cls, user_id: int) -> int:
        """
        Return the current fail_count for a user in auto_recheck_state, or 0 if no row.
        """
        async with cls.get_connection() as db:
            cur = await db.execute(
                "SELECT fail_count FROM auto_recheck_state WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    @classmethod
    async def initialize(cls, db_path: Optional[str] = None):
        async with cls._lock:
            if cls._initialized:
                return
            if db_path:
                cls._db_path = db_path
                # No need to keep the connection open after initialization
            async with aiosqlite.connect(cls._db_path) as db:
                await cls._create_tables(db)
            cls._initialized = True
            logger.info("Database initialized.")

    @classmethod
    async def _create_tables(cls, db):
        # Create verification table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS verification (
                user_id INTEGER PRIMARY KEY,
                rsi_handle TEXT NOT NULL,
                membership_status TEXT NOT NULL,
                last_updated INTEGER NOT NULL,
                needs_reverify INTEGER NOT NULL DEFAULT 0,
                needs_reverify_at INTEGER
            )
            """
        )
        cursor = await db.execute("PRAGMA table_info(verification)")
        columns = [row[1] for row in await cursor.fetchall()]
        last_recheck_exists = "last_recheck" in columns
        # Backfill new columns if migration on existing DB
        if "needs_reverify" not in columns:
            try:
                await db.execute(
                    "ALTER TABLE verification ADD COLUMN needs_reverify INTEGER NOT NULL DEFAULT 0"
                )
                logger.info("Added column verification.needs_reverify")
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add needs_reverify column (maybe already exists): {e}")
            except Exception as e:
                logger.error(f"Unexpected error adding needs_reverify column: {e}")
        if "needs_reverify_at" not in columns:
            try:
                await db.execute(
                    "ALTER TABLE verification ADD COLUMN needs_reverify_at INTEGER"
                )
                logger.info("Added column verification.needs_reverify_at")
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add needs_reverify_at column (maybe already exists): {e}")
            except Exception as e:
                logger.error(f"Unexpected error adding needs_reverify_at column: {e}")
        if last_recheck_exists:
            logger.info("Found legacy last_recheck column; will migrate data.")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limits (
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                first_attempt INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, action),
                FOREIGN KEY (user_id) REFERENCES verification(user_id)
            )
            """
        )

        if last_recheck_exists:
            await db.execute(
                """
                INSERT OR IGNORE INTO rate_limits(user_id, action, attempt_count, first_attempt)
                SELECT user_id, 'recheck', 1, last_recheck FROM verification WHERE last_recheck > 0
                """
            )
            await db.commit()
            # Safe SQLite migration: some SQLite versions/environments don't support
            # ALTER TABLE ... DROP COLUMN. Instead, create a temp table with the
            # Desired schema, copy rows (excluding the legacy column), drop the
            # Old table and rename the temp table.
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_tmp (
                    user_id INTEGER PRIMARY KEY,
                    rsi_handle TEXT NOT NULL,
                    membership_status TEXT NOT NULL,
                    last_updated INTEGER NOT NULL,
                    needs_reverify INTEGER NOT NULL DEFAULT 0,
                    needs_reverify_at INTEGER
                )
            """
            )
            # Copy data from old table excluding last_recheck. Use INSERT OR REPLACE
            # So the operation is effectively idempotent if run multiple times.
            await db.execute(
                """
                INSERT OR REPLACE INTO verification_tmp (user_id, rsi_handle, membership_status, last_updated)
                SELECT user_id, rsi_handle, membership_status, last_updated FROM verification
            """
            )
            await db.commit()
            # Replace the old table with the temp table. Use IF EXISTS to be
            # Tolerant of repeated runs.
            await db.execute("DROP TABLE IF EXISTS verification")
            await db.execute("ALTER TABLE verification_tmp RENAME TO verification")
            await db.commit()

            # Create or update voice tables
            # In _create_tables method
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_voice_channels (
                voice_channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL
            )
        """
        )
        # Create voice cooldown table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_created INTEGER NOT NULL
            )
        """
        )
        # Create settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """
        )
        # Create channel_settings table (with lock column)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_settings (
                user_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                user_limit INTEGER,
                lock INTEGER DEFAULT 0
            )
        """
        )
        # Create channel_permissions table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_permissions (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user' or 'role'
                permission TEXT NOT NULL,   -- 'permit' or 'reject'
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """
        )
        # Create channel_ptt_settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_ptt_settings (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user', 'role', or 'everyone'
                ptt_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user' or 'role'
                priority_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """
        )

        # Create channel_soundboard_settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_soundboard_settings (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user', 'role', or 'everyone'
                soundboard_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """
        )

        # Auto-recheck scheduler state
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_recheck_state (
                user_id INTEGER PRIMARY KEY,
                last_auto_recheck INTEGER DEFAULT 0,
                next_retry_at INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                last_error TEXT
            )
        """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ars_next ON auto_recheck_state(next_retry_at)"
        )
        await db.commit()

        # Create announcement_events table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS announcement_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                announced_at INTEGER
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ae_pending ON announcement_events(announced_at)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ae_created ON announcement_events(created_at)"
        )

        await db.commit()

        # Persisted warnings: track guilds we've already reported missing configured roles
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS missing_role_warnings (
                guild_id INTEGER PRIMARY KEY,
                reported_at INTEGER NOT NULL
            )
        """
        )
        await db.commit()

    @classmethod
    @asynccontextmanager
    async def get_connection(cls):
        """
        Asynchronous context manager for database connections.
        """
        if not cls._initialized:
            await cls.initialize()
        async with aiosqlite.connect(cls._db_path) as db:
            yield db

    @classmethod
    async def fetch_rate_limit(cls, user_id: int, action: str):
        async with cls.get_connection() as db:
            cursor = await db.execute(
                "SELECT attempt_count, first_attempt FROM rate_limits WHERE user_id = ? AND action = ?",
                (user_id, action),
            )
            return await cursor.fetchone()

    @classmethod
    async def has_reported_missing_roles(cls, guild_id: int) -> bool:
        """Return True if we've previously recorded a missing-role warning for this guild."""
        async with cls.get_connection() as db:
            cursor = await db.execute(
                "SELECT 1 FROM missing_role_warnings WHERE guild_id = ?", (guild_id,)
            )
            return (await cursor.fetchone()) is not None

    @classmethod
    async def mark_reported_missing_roles(cls, guild_id: int):
        """Record that we've warned about missing configured roles for this guild."""
        now = int(time.time())
        async with cls.get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO missing_role_warnings (guild_id, reported_at) VALUES (?, ?)",
                (guild_id, now),
            )
            await db.commit()

    @classmethod
    async def increment_rate_limit(cls, user_id: int, action: str):
        now = int(time.time())
        async with cls.get_connection() as db:
            await db.execute(
                """
                INSERT INTO rate_limits(user_id, action, attempt_count, first_attempt)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, action) DO UPDATE SET attempt_count=attempt_count+1
                """,
                (user_id, action, now),
            )
            await db.commit()

    @classmethod
    async def reset_rate_limit(
        cls, user_id: Optional[int] = None, action: Optional[str] = None
    ):
        async with cls.get_connection() as db:
            if user_id is None:
                await db.execute("DELETE FROM rate_limits")
            elif action is None:
                await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ?", (user_id,)
                )
            else:
                await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ? AND action = ?",
                    (user_id, action),
                )
            await db.commit()

    @classmethod
    async def upsert_auto_recheck_success(
        cls, user_id: int, next_retry_at: int, now: int, new_fail_count: int = 0
    ):
        async with cls.get_connection() as db:
            await db.execute(
                """
                INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count, last_error)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_auto_recheck=excluded.last_auto_recheck,
                    next_retry_at=excluded.next_retry_at,
                    fail_count=excluded.fail_count,
                    last_error=NULL
            """,
                (user_id, now, next_retry_at, new_fail_count),
            )
            await db.commit()

    @classmethod
    async def upsert_auto_recheck_failure(
        cls,
        user_id: int,
        next_retry_at: int,
        now: int,
        error_msg: str,
        inc: bool = True,
    ):
        async with cls.get_connection() as db:
            if inc:
                await db.execute(
                    """
                    INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count, last_error)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_auto_recheck=excluded.last_auto_recheck,
                        next_retry_at=excluded.next_retry_at,
                        fail_count=fail_count+1,
                        last_error=excluded.last_error
                """,
                    (user_id, now, next_retry_at, error_msg[:500]),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count, last_error)
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_auto_recheck=excluded.last_auto_recheck,
                        next_retry_at=excluded.next_retry_at,
                        last_error=excluded.last_error
                """,
                    (user_id, now, next_retry_at, error_msg[:500]),
                )
            await db.commit()

    @classmethod
    async def get_due_auto_rechecks(cls, now: int, limit: int):
        """
        Returns list of (user_id, rsi_handle, membership_status) that are due for auto recheck.
        If a user has no row in auto_recheck_state, treat as due (bootstrap on first touch).
        """
        async with cls.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT v.user_id, v.rsi_handle, v.membership_status
                FROM verification v
                LEFT JOIN auto_recheck_state s ON s.user_id = v.user_id
                WHERE COALESCE(s.next_retry_at, 0) <= ?
                  AND v.needs_reverify = 0
                ORDER BY COALESCE(s.last_auto_recheck, 0) ASC
                LIMIT ?
            """,
                (now, limit),
            )
            return await cursor.fetchall()

    # 404 username change helpers
    @classmethod
    async def flag_needs_reverify(cls, user_id: int, now: int) -> bool:
        """Set needs_reverify flag. Returns True if row updated (was newly flagged)."""
        async with cls.get_connection() as db:
            cur = await db.execute(
                "UPDATE verification SET needs_reverify=1, needs_reverify_at=? WHERE user_id=? AND needs_reverify=0",
                (now, user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    @classmethod
    async def clear_needs_reverify(cls, user_id: int):
        async with cls.get_connection() as db:
            await db.execute(
                "UPDATE verification SET needs_reverify=0, needs_reverify_at=NULL WHERE user_id=?",
                (user_id,),
            )
            await db.commit()

    @classmethod
    async def unschedule_auto_recheck(cls, user_id: int):
        """Remove any auto-recheck state for a user (stop further auto checks)."""
        async with cls.get_connection() as db:
            await db.execute(
                "DELETE FROM auto_recheck_state WHERE user_id = ?", (user_id,)
            )
            await db.commit()
