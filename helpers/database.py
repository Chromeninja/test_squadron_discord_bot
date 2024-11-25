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
        # Simplify voice tables since the bot is for a single server
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_voice_channels (
                user_id INTEGER PRIMARY KEY,
                voice_channel_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_created INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                user_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                user_limit INTEGER,
                permissions TEXT  -- JSON string to store permissions like PTT settings
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
