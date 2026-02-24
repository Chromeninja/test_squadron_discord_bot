"""
Tests for the pending_role_sync queue in RoleDelegationService.

Exercises enqueue, dequeue, retry back-off, and success/failure paths
using a real in-memory SQLite database so we validate actual SQL.
"""

import time

import pytest
import pytest_asyncio

from services.db.database import Database
from services.role_delegation_service import RoleDelegationService


@pytest_asyncio.fixture()
async def temp_db(tmp_path):
    """Initialize Database to a temp file so pending_role_sync table exists."""
    orig_path = Database._db_path
    orig_initialized = Database._initialized

    Database._initialized = False
    Database._db_path = None  # type: ignore[assignment]
    db_file = tmp_path / "test_sync.db"
    await Database.initialize(str(db_file))

    yield str(db_file)

    Database._db_path = orig_path
    Database._initialized = orig_initialized


# ---------------------------------------------------------------------------
# Enqueue + dequeue
# ---------------------------------------------------------------------------


class TestPendingRoleSyncQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_get_due(self, temp_db):
        """Enqueued items are returned by get_due_pending_syncs after retry time."""
        await RoleDelegationService._enqueue_pending_sync(
            guild_id=100,
            user_id=200,
            role_id=300,
            action="grant",
            reason="test reason",
            error="Forbidden",
        )

        # The enqueue sets next_retry_at = now + 60, so nothing is due yet
        due_now = await RoleDelegationService.get_due_pending_syncs()
        assert len(due_now) == 0

        # Fast-forward: set next_retry_at to the past
        async with Database.get_connection() as db:
            await db.execute("UPDATE pending_role_sync SET next_retry_at = 0")
            await db.commit()

        due_now = await RoleDelegationService.get_due_pending_syncs()
        assert len(due_now) == 1

        row = due_now[0]
        assert row["guild_id"] == 100
        assert row["user_id"] == 200
        assert row["role_id"] == 300
        assert row["action"] == "grant"
        assert row["reason"] == "test reason"
        assert row["fail_count"] == 1

    @pytest.mark.asyncio
    async def test_get_due_respects_limit(self, temp_db):
        """Only `limit` rows are returned."""
        for i in range(5):
            await RoleDelegationService._enqueue_pending_sync(
                guild_id=1,
                user_id=i,
                role_id=10,
                action="grant",
            )
        # Expire them all
        async with Database.get_connection() as db:
            await db.execute("UPDATE pending_role_sync SET next_retry_at = 0")
            await db.commit()

        result = await RoleDelegationService.get_due_pending_syncs(limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_due_empty_table(self, temp_db):
        """No rows returns an empty list, not an error."""
        result = await RoleDelegationService.get_due_pending_syncs()
        assert result == []


# ---------------------------------------------------------------------------
# Mark success / failure
# ---------------------------------------------------------------------------


class TestMarkSyncOutcome:
    @pytest.mark.asyncio
    async def test_mark_success_deletes_row(self, temp_db):
        await RoleDelegationService._enqueue_pending_sync(
            guild_id=1,
            user_id=2,
            role_id=3,
            action="grant",
        )
        # Get the row id
        async with Database.get_connection() as db:
            await db.execute("UPDATE pending_role_sync SET next_retry_at = 0")
            await db.commit()

        rows = await RoleDelegationService.get_due_pending_syncs()
        assert len(rows) == 1
        row_id = rows[0]["id"]

        await RoleDelegationService.mark_sync_success(row_id)

        # Row should be gone
        remaining = await RoleDelegationService.get_due_pending_syncs()
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_mark_failure_bumps_count_and_backoff(self, temp_db):
        await RoleDelegationService._enqueue_pending_sync(
            guild_id=1,
            user_id=2,
            role_id=3,
            action="revoke",
        )
        async with Database.get_connection() as db:
            await db.execute("UPDATE pending_role_sync SET next_retry_at = 0")
            await db.commit()

        rows = await RoleDelegationService.get_due_pending_syncs()
        row_id = rows[0]["id"]
        original_fail = rows[0]["fail_count"]  # 1 from enqueue

        await RoleDelegationService.mark_sync_failure(row_id, "still forbidden")

        # Row still exists with bumped fail_count and pushed-out retry
        async with Database.get_connection() as db:
            cur = await db.execute(
                "SELECT fail_count, next_retry_at, last_error FROM pending_role_sync WHERE id = ?",
                (row_id,),
            )
            row = await cur.fetchone()

        assert row is not None
        assert row[0] == original_fail + 1  # fail_count incremented
        assert row[1] > int(time.time()) - 5  # next_retry_at pushed forward
        assert row[2] == "still forbidden"
