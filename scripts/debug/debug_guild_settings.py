"""Debug script to test guild settings directly.

Developer utility for manual database checks; not a unit test.
"""

import asyncio
import json
import tempfile

from services.db.database import Database


async def test_direct_db():
    """Test guild settings storage directly."""
    # Create temp database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    print(f"Using temp database: {db_path}")

    # Initialize database
    await Database.initialize(db_path)

    # Test direct insertion
    guild_id = 12345
    key = "test.setting"
    value = {"nested": "value"}

    async with Database.get_connection() as db:
        # Insert setting
        await db.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (guild_id, key, json.dumps(value))
        )
        await db.commit()

        # Retrieve setting
        async with db.execute(
            "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
            (guild_id, key)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            retrieved_value = json.loads(row[0])
            print(f"Success! Retrieved: {retrieved_value}")
        else:
            print("Failed! No row found")


if __name__ == "__main__":
    asyncio.run(test_direct_db())
