import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import pytest
import aiosqlite

from helpers.database import Database

@pytest.mark.asyncio
async def test_create_tables_adds_last_recheck_when_missing():
    async with aiosqlite.connect(":memory:") as db:
        # simulate old schema without last_recheck column
        await db.execute(
            """
            CREATE TABLE verification (
                user_id INTEGER PRIMARY KEY,
                rsi_handle TEXT NOT NULL,
                membership_status TEXT NOT NULL,
                last_updated INTEGER NOT NULL
            )
            """
        )
        await db.commit()

        await Database._create_tables(db)

        cursor = await db.execute("PRAGMA table_info(verification)")
        columns = {row[1]: row[4] for row in await cursor.fetchall()}
        assert "last_recheck" in columns
        assert columns["last_recheck"] == "0"


@pytest.mark.asyncio
async def test_create_tables_idempotent_on_new_db():
    async with aiosqlite.connect(":memory:") as db:
        await Database._create_tables(db)
        await Database._create_tables(db)

        cursor = await db.execute("PRAGMA table_info(verification)")
        column_names = [row[1] for row in await cursor.fetchall()]
        assert column_names.count("last_recheck") == 1

