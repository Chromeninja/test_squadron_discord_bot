# helpers/database.py

import aiosqlite
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
                last_updated INTEGER NOT NULL
            )
            """
        )
        cursor = await db.execute("PRAGMA table_info(verification)")
        columns = [row[1] for row in await cursor.fetchall()]
        last_recheck_exists = "last_recheck" in columns
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
            await db.execute("ALTER TABLE verification DROP COLUMN last_recheck")
            await db.commit()

        # Create or update voice tables
        # In _create_tables method
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_voice_channels (
                voice_channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL
            )
        """)
        # Create voice cooldown table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_created INTEGER NOT NULL
            )
        """)
        # Create settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Create channel_settings table (with lock column)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                user_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                user_limit INTEGER,
                lock INTEGER DEFAULT 0
            )
        """)
        # Create channel_permissions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_permissions (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user' or 'role'
                permission TEXT NOT NULL,   -- 'permit' or 'reject'
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """)
        # Create channel_ptt_settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_ptt_settings (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user', 'role', or 'everyone'
                ptt_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user' or 'role'
                priority_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """)

        # Create channel_soundboard_settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_soundboard_settings (
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,  -- 'user', 'role', or 'everyone'
                soundboard_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, target_id, target_type)
            )
        """)
       
        # Create announcement_events table
        await db.execute("""
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
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ae_pending ON announcement_events(announced_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ae_created ON announcement_events(created_at)")

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
    async def reset_rate_limit(cls, user_id: Optional[int] = None, action: Optional[str] = None):
        async with cls.get_connection() as db:
            if user_id is None:
                await db.execute("DELETE FROM rate_limits")
            elif action is None:
                await db.execute("DELETE FROM rate_limits WHERE user_id = ?", (user_id,))
            else:
                await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ? AND action = ?",
                    (user_id, action),
                )
            await db.commit()
