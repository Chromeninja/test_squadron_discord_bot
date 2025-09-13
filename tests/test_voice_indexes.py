"""
Test that verifies new composite indexes are created correctly.
"""

import pytest

from services.db.database import Database


@pytest.mark.asyncio
async def test_composite_indexes_created(temp_db) -> None:
    """Test that new composite indexes are created by schema initialization."""
    async with Database.get_connection() as db:
        # Check that our new composite indexes exist
        cursor = await db.execute("PRAGMA index_list(user_voice_channels)")
        indexes = await cursor.fetchall()
        index_names = [idx[1] for idx in indexes]

        assert (
            "idx_uvc_owner_scope" in index_names
        ), "idx_uvc_owner_scope index should exist"

        # Check channel_settings indexes
        cursor = await db.execute("PRAGMA index_list(channel_settings)")
        indexes = await cursor.fetchall()
        index_names = [idx[1] for idx in indexes]

        assert (
            "idx_cs_scope_user" in index_names
        ), "idx_cs_scope_user index should exist"

        # Check channel_permissions indexes
        cursor = await db.execute("PRAGMA index_list(channel_permissions)")
        indexes = await cursor.fetchall()
        index_names = [idx[1] for idx in indexes]

        assert (
            "idx_cp_scope_user_target" in index_names
        ), "idx_cp_scope_user_target index should exist"


@pytest.mark.asyncio
async def test_pragma_settings_applied(temp_db) -> None:
    """Test that PRAGMA settings are applied correctly."""
    async with Database.get_connection() as db:
        # Check foreign keys are enabled
        cursor = await db.execute("PRAGMA foreign_keys")
        result = await cursor.fetchone()
        assert result[0] == 1, "Foreign keys should be enabled"

        # Check journal mode is WAL
        cursor = await db.execute("PRAGMA journal_mode")
        result = await cursor.fetchone()
        assert result[0] == "wal", "Journal mode should be WAL"

        # Check synchronous is NORMAL
        cursor = await db.execute("PRAGMA synchronous")
        result = await cursor.fetchone()
        assert result[0] == 1, "Synchronous should be NORMAL (1)"
