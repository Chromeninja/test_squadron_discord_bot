import aiosqlite
import pytest

from services.db.schema import init_schema


@pytest.mark.asyncio
async def test_init_schema_creates_expected_tables() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await init_schema(db)

        # verification table exists without the removed membership_status column
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
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
        )
        row = await cursor.fetchone()
        assert row and row[0] == 1


@pytest.mark.asyncio
async def test_init_schema_backfills_legacy_ticket_categories_channel_id() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """
            CREATE TABLE ticket_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                welcome_message TEXT DEFAULT '',
                role_ids TEXT DEFAULT '[]',
                emoji TEXT DEFAULT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.commit()

        await init_schema(db)

        cursor = await db.execute("PRAGMA table_info(ticket_categories)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "channel_id" in columns
        assert "prerequisite_role_ids_all" in columns
        assert "prerequisite_role_ids_any" in columns

        cursor = await db.execute(
            "PRAGMA index_info(idx_ticket_categories_guild_channel)"
        )
        index_columns = [row[2] for row in await cursor.fetchall()]
        assert index_columns == ["guild_id", "channel_id"]
