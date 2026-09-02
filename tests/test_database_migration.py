import json

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


@pytest.mark.asyncio
async def test_init_schema_migrates_legacy_ticket_settings_idempotently() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await init_schema(db)
        await db.executemany(
            "INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            [
                (123, "tickets.channel_id", "456"),
                (123, "tickets.panel_message_id", "789"),
            ],
        )
        await db.execute(
            "INSERT INTO ticket_categories (guild_id, channel_id, name) VALUES (?, ?, ?)",
            (123, 0, "Support"),
        )
        await db.commit()

        await init_schema(db)
        await init_schema(db)

        cursor = await db.execute(
            "SELECT channel_id FROM ticket_channel_configs WHERE guild_id = ?", (123,)
        )
        assert [row[0] for row in await cursor.fetchall()] == [456]
        cursor = await db.execute(
            "SELECT channel_id FROM ticket_categories WHERE guild_id = ?", (123,)
        )
        assert [row[0] for row in await cursor.fetchall()] == [456]
        cursor = await db.execute(
            "SELECT key, value FROM guild_settings WHERE guild_id = ? ORDER BY key", (123,)
        )
        assert await cursor.fetchall() == [("tickets.panel_message_id.456", "789")]


@pytest.mark.asyncio
async def test_init_schema_migrates_legacy_delegation_prerequisites() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await init_schema(db)
        await db.execute(
            "INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (
                123,
                "roles.delegation_policies",
                '[{"target_role_id": "2", "prerequisite_role_ids": ["1"]}]',
            ),
        )
        await db.commit()

        await init_schema(db)
        cursor = await db.execute(
            "SELECT value FROM guild_settings WHERE guild_id = 123 "
            "AND key = 'roles.delegation_policies'"
        )
        value = (await cursor.fetchone())[0]
        assert json.loads(value) == [
            {"target_role_id": "2", "prerequisite_role_ids_all": ["1"]}
        ]


@pytest.mark.asyncio
async def test_init_schema_backfills_legacy_managed_event_display_columns() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """
            CREATE TABLE managed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_event_id TEXT DEFAULT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT NULL,
                announcement_message TEXT DEFAULT NULL,
                scheduled_start_time TEXT NOT NULL,
                scheduled_end_time TEXT DEFAULT NULL,
                entity_type TEXT NOT NULL DEFAULT 'voice',
                channel_id TEXT DEFAULT NULL,
                location TEXT DEFAULT NULL,
                announcement_channel_id TEXT DEFAULT NULL,
                signup_role_ids TEXT NOT NULL DEFAULT '[]',
                announcement_message_id TEXT DEFAULT NULL,
                signup_message_id TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                revision INTEGER NOT NULL DEFAULT 1,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                sync_error TEXT DEFAULT NULL,
                user_count_current INTEGER NOT NULL DEFAULT 0,
                user_count_last_synced_at INTEGER DEFAULT NULL,
                last_synced_at INTEGER DEFAULT NULL,
                last_projected_hash TEXT DEFAULT NULL,
                source TEXT NOT NULL DEFAULT 'dashboard',
                created_by_user_id TEXT DEFAULT NULL,
                created_by_name TEXT DEFAULT NULL,
                updated_by_user_id TEXT DEFAULT NULL,
                updated_by_name TEXT DEFAULT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                deleted_at INTEGER DEFAULT NULL,
                recurrence_rule TEXT DEFAULT NULL,
                recurrence_rule_payload TEXT DEFAULT NULL
            )
            """
        )
        await db.commit()

        await init_schema(db)

        cursor = await db.execute("PRAGMA table_info(managed_events)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "channel_name" in columns
        assert "image_url" in columns
        assert "signup_role_ids" not in columns


@pytest.mark.asyncio
async def test_init_schema_backfills_legacy_verification_org_columns() -> None:
    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """
            CREATE TABLE verification (
                user_id INTEGER PRIMARY KEY,
                rsi_handle TEXT NOT NULL UNIQUE,
                last_updated INTEGER DEFAULT 0,
                verification_payload TEXT,
                needs_reverify INTEGER DEFAULT 0,
                needs_reverify_at INTEGER DEFAULT 0,
                community_moniker TEXT
            )
            """
        )
        await db.commit()

        await init_schema(db)

        cursor = await db.execute("PRAGMA table_info(verification)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "main_orgs" in columns
        assert "affiliate_orgs" in columns
