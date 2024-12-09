# helpers/database.py

import aiosqlite
import asyncio
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS verification (
                user_id INTEGER PRIMARY KEY,
                rsi_handle TEXT NOT NULL,
                membership_status TEXT NOT NULL,
                last_updated INTEGER NOT NULL
            )
        """)
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
