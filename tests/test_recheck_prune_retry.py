import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio

from cogs.recheck import AutoRecheck
from helpers.database import Database


class FakeMember:
    def __init__(self, user_id=42):
        self.id = user_id


class FlakyGuild:
    """Simulates a guild where get_member is a cache that may miss once.

    On the first call to get_member it returns None. On subsequent calls it
    can be configured to return a member or always None. fetch_member can be
    configured similarly.
    """

    def __init__(self, member_on_retry: bool = True, fetch_on_first: bool = False):
        self._calls = {"get": 0, "fetch": 0}
        self._member_on_retry = member_on_retry
        self._fetch_on_first = fetch_on_first

    def get_member(self, user_id: int):
        self._calls["get"] += 1
        # Simulate cache miss on first call
        if self._calls["get"] == 1:
            return None
        return FakeMember(user_id) if self._member_on_retry else None

    async def fetch_member(self, user_id: int):
        self._calls["fetch"] += 1
        if self._fetch_on_first and self._calls["fetch"] == 1:
            return FakeMember(user_id)
        # Otherwise behave like the get_member retry
        return FakeMember(user_id) if self._member_on_retry else None


@pytest.mark.asyncio
async def test_no_prune_on_transient_cache_miss(temp_db):
    """If the member is found on the retry after a short sleep, rows must not be deleted."""
    # Initialize DB (temp_db fixture already initialized)
    # Insert verification and auto_recheck_state rows
    async with Database.get_connection() as db:
        await db.execute(
            "INSERT INTO verification (user_id, rsi_handle, membership_status, last_updated) VALUES (?, ?, ?, ?)",
            (123, "handle", "member", 1),
        )
        await db.execute(
            "INSERT INTO auto_recheck_state (user_id, last_auto_recheck, next_retry_at, fail_count) VALUES (?, ?, ?, ?)",
            (123, 0, 0, 0),
        )
        await db.commit()

    # Create a bot-like namespace required by AutoRecheck
    bot_ns = SimpleNamespace()
    bot_ns.config = {}
    bot_ns.guilds = [FlakyGuild(member_on_retry=True, fetch_on_first=False)]

    cog = AutoRecheck(bot_ns)

    member = await cog._fetch_member_or_prune(bot_ns.guilds[0], 123)
    assert member is not None

    # Ensure rows remain
    async with Database.get_connection() as db:
        cur = await db.execute("SELECT 1 FROM verification WHERE user_id = ?", (123,))
        assert await cur.fetchone() is not None
        cur = await db.execute(
            "SELECT 1 FROM auto_recheck_state WHERE user_id = ?", (123,)
        )
        assert await cur.fetchone() is not None


@pytest.mark.asyncio
async def test_prune_when_member_absent_after_retry(temp_db):
    """If member is still missing after retry, rows should be deleted."""
    async with Database.get_connection() as db:
        await db.execute(
            "INSERT OR REPLACE INTO verification (user_id, rsi_handle, membership_status, last_updated) VALUES (?, ?, ?, ?)",
            (456, "handle2", "member", 1),
        )
        await db.execute(
            "INSERT OR REPLACE INTO auto_recheck_state (user_id, last_auto_recheck, next_retry_at, fail_count) VALUES (?, ?, ?, ?)",
            (456, 0, 0, 0),
        )
        await db.commit()

    bot_ns = SimpleNamespace()
    bot_ns.config = {}
    # Simulate both get_member and fetch_member failing even on retry
    bot_ns.guilds = [FlakyGuild(member_on_retry=False, fetch_on_first=False)]

    cog = AutoRecheck(bot_ns)

    member = await cog._fetch_member_or_prune(bot_ns.guilds[0], 456)
    assert member is None

    # Ensure rows deleted
    async with Database.get_connection() as db:
        cur = await db.execute("SELECT 1 FROM verification WHERE user_id = ?", (456,))
        assert await cur.fetchone() is None
        cur = await db.execute(
            "SELECT 1 FROM auto_recheck_state WHERE user_id = ?", (456,)
        )
        assert await cur.fetchone() is None
