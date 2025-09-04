# Helpers/database.py

import aiosqlite
import sqlite3
import asyncio
import time
from typing import Optional
from helpers.logger import get_logger
from contextlib import asynccontextmanager
from helpers.schema import init_schema

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
                # Enable foreign key constraints
                await db.execute("PRAGMA foreign_keys=ON")
                # Initialize schema using the centralized schema module
                await init_schema(db)
                # Run compatibility migrations on fresh DB path
                # _create_tables is safe to call multiple times and also used by tests
                try:
                    await cls._create_tables(db)
                except Exception:
                    # If migration logic not applicable, ignore; tests may call _create_tables directly
                    pass
            cls._initialized = True
            logger.info("Database initialized.")

    @classmethod
    async def _create_tables(cls, db: aiosqlite.Connection):
        """Compatibility/migration helper used by tests.

        Ensures rate_limits exists and migrates legacy verification.last_recheck into rate_limits
        (this mirrors migrations/004_create_rate_limits.sql behavior).
        """
        # Ensure rate_limits table exists
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limits (
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                first_attempt INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, action)
            )
            """
        )
        # If verification has last_recheck column, migrate values
        try:
            cursor = await db.execute("PRAGMA table_info(verification)")
            rows = await cursor.fetchall()
            cols = [r[1] for r in rows]
            if "last_recheck" in cols:
                # Migrate last_recheck values into rate_limits
                await db.execute(
                    "INSERT OR IGNORE INTO rate_limits(user_id, action, attempt_count, first_attempt) "
                    "SELECT user_id, 'recheck', 1, last_recheck FROM verification WHERE last_recheck > 0"
                )

                # Recreate verification table without last_recheck while preserving other columns and types
                # Build column definitions from PRAGMA table_info
                new_cols = []
                select_cols = []
                pk_clause = None
                for r in rows:
                    cid, name, col_type, notnull, dflt_value, pk = r
                    if name == "last_recheck":
                        continue
                    col_def = f"{name} {col_type or 'TEXT'}"
                    if pk:
                        col_def += " PRIMARY KEY"
                        pk_clause = name
                    if notnull:
                        col_def += " NOT NULL"
                    if dflt_value is not None:
                        col_def += f" DEFAULT {dflt_value}"
                    new_cols.append(col_def)
                    select_cols.append(name)

                await db.execute("PRAGMA foreign_keys=OFF")
                await db.execute(f"CREATE TABLE IF NOT EXISTS _verification_new ({', '.join(new_cols)})")
                await db.execute(
                    f"INSERT INTO _verification_new({', '.join(select_cols)}) SELECT {', '.join(select_cols)} FROM verification"
                )
                await db.execute("DROP TABLE verification")
                await db.execute("ALTER TABLE _verification_new RENAME TO verification")
                await db.execute("PRAGMA foreign_keys=ON")
            await db.commit()
        except Exception:
            await db.rollback()

    @classmethod
    @asynccontextmanager
    async def get_connection(cls):
        """
        Get a connection to the database with optimized settings.
        
        Usage:
            async with Database.get_connection() as db:
                await db.execute("SELECT * FROM table")
        """
        if not cls._initialized:
            await cls.initialize()
        async with aiosqlite.connect(cls._db_path) as db:
            # Optimize database performance and reliability
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA busy_timeout=5000")
            db.row_factory = aiosqlite.Row
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

    # 404 handle change helpers (legacy 'username_404' module name retained for backward compatibility)
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
