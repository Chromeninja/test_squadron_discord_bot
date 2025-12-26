"""
Database Factories

Provides helper functions for seeding test databases with consistent data.
Use these to set up database state for integration and contract tests.
"""

from __future__ import annotations

from typing import Any

from services.db.database import Database


async def seed_guild_settings(
    guild_id: int = 123,
    bot_admin_roles: list[int] | None = None,
    moderator_roles: list[int] | None = None,
    staff_roles: list[int] | None = None,
    extra_settings: dict[str, Any] | None = None,
) -> None:
    """
    Seed guild settings into the database.

    Args:
        guild_id: The guild ID to seed settings for
        bot_admin_roles: List of role IDs for bot admins
        moderator_roles: List of role IDs for moderators
        staff_roles: List of role IDs for staff
        extra_settings: Additional key-value pairs to insert

    Examples:
        await seed_guild_settings(
            guild_id=123,
            bot_admin_roles=[999111222],
            moderator_roles=[999111223],
        )
    """
    import json

    admin_roles = bot_admin_roles or [999111222]
    mod_roles = moderator_roles or [999111223]
    staff = staff_roles or [999111224]

    settings = [
        (guild_id, "roles.bot_admins", json.dumps([str(r) for r in admin_roles])),
        (guild_id, "roles.moderators", json.dumps([str(r) for r in mod_roles])),
        (guild_id, "roles.staff", json.dumps([str(r) for r in staff])),
    ]

    if extra_settings:
        for key, value in extra_settings.items():
            settings.append((guild_id, key, json.dumps(value)))

    async with Database.get_connection() as db:
        for guild, key, value in settings:
            await db.execute(
                """
                INSERT INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
                """,
                (guild, key, value),
            )
        await db.commit()


async def seed_verification_records(
    records: list[dict[str, Any]] | None = None,
) -> None:
    """
    Seed verification records into the database.

    Args:
        records: List of verification record dicts with keys:
            - user_id: Discord user ID
            - rsi_handle: RSI handle
            - last_updated: Unix timestamp (optional, defaults to current time)
            - community_moniker: Display name (optional)
            - main_orgs: JSON string of main orgs (optional)
            - affiliate_orgs: JSON string of affiliate orgs (optional)

    Examples:
        await seed_verification_records([
            {"user_id": 123456789, "rsi_handle": "TestUser", "main_orgs": '["TEST"]'},
            {"user_id": 987654321, "rsi_handle": "AffiliateUser", "affiliate_orgs": '["TEST"]'},
        ])
    """
    import time

    if records is None:
        records = [
            {
                "user_id": 123456789,
                "rsi_handle": "TestUser1",
                "main_orgs": '["TEST"]',
                "affiliate_orgs": "[]",
            },
            {
                "user_id": 987654321,
                "rsi_handle": "TestUser2",
                "main_orgs": "[]",
                "affiliate_orgs": '["TEST"]',
            },
        ]

    async with Database.get_connection() as db:
        for record in records:
            await db.execute(
                """
                INSERT INTO verification
                (user_id, rsi_handle, last_updated, community_moniker, main_orgs, affiliate_orgs)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    rsi_handle = excluded.rsi_handle,
                    last_updated = excluded.last_updated,
                    community_moniker = excluded.community_moniker,
                    main_orgs = excluded.main_orgs,
                    affiliate_orgs = excluded.affiliate_orgs
                """,
                (
                    record["user_id"],
                    record["rsi_handle"],
                    record.get("last_updated", int(time.time())),
                    record.get("community_moniker"),
                    record.get("main_orgs", "[]"),
                    record.get("affiliate_orgs", "[]"),
                ),
            )
        await db.commit()


async def seed_voice_channels(
    channels: list[dict[str, Any]] | None = None,
) -> None:
    """
    Seed voice channel records into the database.

    Args:
        channels: List of voice channel dicts with keys:
            - guild_id: Guild ID
            - jtc_channel_id: Join-to-create channel ID
            - owner_id: Owner's user ID
            - voice_channel_id: Created voice channel ID
            - created_at: Unix timestamp (optional)
            - last_activity: Unix timestamp (optional)
            - is_active: Whether channel is active (optional, defaults to 1)

    Examples:
        await seed_voice_channels([
            {
                "guild_id": 123,
                "jtc_channel_id": 456,
                "owner_id": 789,
                "voice_channel_id": 101112,
                "is_active": 1,
            },
        ])
    """
    import time

    if channels is None:
        channels = [
            {
                "guild_id": 1111,
                "jtc_channel_id": 2222,
                "owner_id": 123456789,
                "voice_channel_id": 3333,
                "is_active": 1,
            },
        ]

    current_time = int(time.time())

    async with Database.get_connection() as db:
        for channel in channels:
            await db.execute(
                """
                INSERT INTO voice_channels
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(voice_channel_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    last_activity = excluded.last_activity,
                    is_active = excluded.is_active
                """,
                (
                    channel["guild_id"],
                    channel["jtc_channel_id"],
                    channel["owner_id"],
                    channel["voice_channel_id"],
                    channel.get("created_at", current_time),
                    channel.get("last_activity", current_time),
                    channel.get("is_active", 1),
                ),
            )
        await db.commit()


async def seed_jtc_preferences(
    preferences: list[dict[str, Any]] | None = None,
) -> None:
    """
    Seed JTC (join-to-create) user preferences into the database.

    Args:
        preferences: List of preference dicts with keys:
            - guild_id: Guild ID
            - user_id: User ID
            - jtc_channel_id: Preferred JTC channel ID
            - updated_at: Unix timestamp (optional)

    Examples:
        await seed_jtc_preferences([
            {"guild_id": 123, "user_id": 456, "jtc_channel_id": 789},
        ])
    """
    import time

    if preferences is None:
        return

    current_time = int(time.time())

    async with Database.get_connection() as db:
        for pref in preferences:
            await db.execute(
                """
                INSERT INTO user_jtc_preferences
                (guild_id, user_id, last_used_jtc_channel_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    last_used_jtc_channel_id = excluded.last_used_jtc_channel_id,
                    updated_at = excluded.updated_at
                """,
                (
                    pref["guild_id"],
                    pref["user_id"],
                    pref.get("last_used_jtc_channel_id", pref.get("jtc_channel_id")),
                    pref.get("updated_at", current_time),
                ),
            )
        await db.commit()


async def get_voice_channel_count(guild_id: int | None = None) -> int:
    """
    Get count of voice channels in database.

    Args:
        guild_id: Optional guild ID to filter by

    Returns:
        Count of voice channel records.
    """
    async with Database.get_connection() as db:
        if guild_id:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM voice_channels WHERE guild_id = ?",
                (guild_id,),
            )
        else:
            cursor = await db.execute("SELECT COUNT(*) FROM voice_channels")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_verification_record(user_id: int) -> dict[str, Any] | None:
    """
    Get a verification record from the database.

    Args:
        user_id: Discord user ID

    Returns:
        Verification record dict or None if not found.
    """
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT user_id, rsi_handle, last_updated, community_moniker, main_orgs, affiliate_orgs
            FROM verification WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "rsi_handle": row[1],
                "last_updated": row[2],
                "community_moniker": row[3],
                "main_orgs": row[4],
                "affiliate_orgs": row[5],
            }
        return None


async def clear_all_voice_channels() -> int:
    """
    Clear all voice channel records from the database.

    Returns:
        Number of records deleted.
    """
    async with Database.get_connection() as db:
        cursor = await db.execute("DELETE FROM voice_channels")
        await db.commit()
        return cursor.rowcount


async def clear_all_verification_records() -> int:
    """
    Clear all verification records from the database.

    Returns:
        Number of records deleted.
    """
    async with Database.get_connection() as db:
        cursor = await db.execute("DELETE FROM verification")
        await db.commit()
        return cursor.rowcount
