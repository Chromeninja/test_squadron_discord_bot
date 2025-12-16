import pytest

from services.db.database import Database


@pytest.mark.asyncio
async def test_database_initialize_and_tables(temp_db) -> None:
    # Database.initialize called by fixture; ensure tables exist and basic ops work
    async with Database.get_connection() as db:
        # Insert into verification
        await db.execute(
            "INSERT OR REPLACE INTO verification(user_id, rsi_handle, last_updated) VALUES (?,?,?)",
            (1, "handle", 0),
        )
        await db.commit()

        # Rate limits basic insert via API
        await Database.increment_rate_limit(1, "verification")
        row = await Database.fetch_rate_limit(1, "verification")
        assert row is not None

        # Reset
        await Database.reset_rate_limit(1, "verification")
        row = await Database.fetch_rate_limit(1, "verification")
        assert row is None
