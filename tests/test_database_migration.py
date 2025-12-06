import aiosqlite
import pytest

from services.db.schema import init_schema


@pytest.mark.asyncio
async def test_init_schema_creates_expected_tables() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await init_schema(db)

        # verification table exists without legacy membership_status
        cursor = await db.execute("PRAGMA table_info(verification)")
        columns = [row[1] for row in await cursor.fetchall()]
        assert "membership_status" not in columns
        assert "verification_payload" in columns

        # rate_limits table exists with primary key columns
        cursor = await db.execute("PRAGMA table_info(rate_limits)")
        rate_limit_cols = {row[1] for row in await cursor.fetchall()}
        assert {"user_id", "action"}.issubset(rate_limit_cols)


@pytest.mark.asyncio
async def test_init_schema_idempotent() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await init_schema(db)
        await init_schema(db)

        cursor = await db.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 0"
        )
        row = await cursor.fetchone()
        assert row and row[0] == 1
