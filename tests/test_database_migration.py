import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import aiosqlite
import pytest

from helpers.database import Database


@pytest.mark.asyncio
async def test_create_tables_creates_rate_limits_and_migrates() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """
            CREATE TABLE verification (
                user_id INTEGER PRIMARY KEY,
                rsi_handle TEXT NOT NULL,
                membership_status TEXT NOT NULL,
                last_updated INTEGER NOT NULL,
                last_recheck INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(

                "INSERT INTO verification(user_id, rsi_handle, membership_status, "
                "last_updated, last_recheck) VALUES (1, 'test', 'member', 0, 123)"

        )
        await db.commit()

        await Database._create_tables(db)

        cursor = await db.execute("PRAGMA table_info(verification)")
        columns = [row[1] for row in await cursor.fetchall()]
        assert "last_recheck" not in columns

        cursor = await db.execute(
            "SELECT attempt_count, first_attempt FROM rate_limits WHERE user_id=1 AND action='recheck'"
        )
        row = await cursor.fetchone()
        assert row == (1, 123)


@pytest.mark.asyncio
async def test_create_tables_idempotent_on_new_db() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await Database._create_tables(db)
        await Database._create_tables(db)

        cursor = await db.execute("PRAGMA table_info(rate_limits)")
        column_names = [row[1] for row in await cursor.fetchall()]
        assert "user_id" in column_names
        assert "action" in column_names
