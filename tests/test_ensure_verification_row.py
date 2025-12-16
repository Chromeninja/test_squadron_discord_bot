"""Test the ensure_verification_row functionality."""

import pytest

from services.db.database import Database


@pytest.mark.asyncio
async def test_ensure_verification_row_creates_minimal_row(temp_db):
    """Test that ensure_verification_row creates a minimal verification row."""
    user_id = 123456

    # Verify no row exists initially
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM verification WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    assert row is None

    # Call ensure_verification_row
    await Database.ensure_verification_row(user_id)

    # Verify row was created with expected values
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT user_id, rsi_handle, last_updated, needs_reverify FROM verification WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == user_id  # user_id
    assert row[1] == ""  # rsi_handle (empty string)
    assert row[2] == 0  # last_updated
    assert row[3] == 0  # needs_reverify


@pytest.mark.asyncio
async def test_ensure_verification_row_idempotent(temp_db):
    """Test that ensure_verification_row is idempotent and doesn't overwrite existing data."""
    user_id = 789012

    # Create a verification row with real data
    async with Database.get_connection() as db:
        await db.execute(
            """INSERT INTO verification (user_id, rsi_handle, last_updated, needs_reverify)
               VALUES (?, ?, ?, ?)""",
            (user_id, "TestHandle", 1234567890, 1),
        )
        await db.commit()

    # Call ensure_verification_row
    await Database.ensure_verification_row(user_id)

    # Verify the existing data wasn't changed
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT user_id, rsi_handle, last_updated, needs_reverify FROM verification WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == user_id
    assert row[1] == "TestHandle"  # Original data preserved
    assert row[2] == 1234567890  # Original data preserved
    assert row[3] == 1  # Original data preserved


@pytest.mark.asyncio
async def test_ensure_verification_row_enables_rate_limits(temp_db):
    """Test that ensure_verification_row enables rate_limits operations without FK errors."""
    user_id = 345678

    # Ensure verification row exists
    await Database.ensure_verification_row(user_id)

    # This should now work without FK constraint errors
    await Database.increment_rate_limit(user_id, "verification")

    # Verify rate limit was recorded
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT user_id, action, attempt_count FROM rate_limits WHERE user_id = ? AND action = ?",
            (user_id, "verification"),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == user_id
    assert row[1] == "verification"
    assert row[2] == 1  # attempt_count
