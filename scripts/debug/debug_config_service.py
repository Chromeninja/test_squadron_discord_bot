"""Debug the config service directly.

This script is a developer-facing utility for ad-hoc testing of the
`ConfigService`. It's not a unit test — keep it under `scripts/debug/`.
"""

import asyncio
import tempfile

from services.config_service import ConfigService
from services.db.database import Database


async def test_config_service():
    """Test config service directly."""
    # Create temp database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    print(f"Using temp database: {db_path}")

    # Initialize database
    await Database.initialize(db_path)

    # Create and initialize config service
    config_service = ConfigService()
    await config_service.initialize()

    guild_id = 12345
    key = "test.setting"
    value = {"nested": "value"}

    print(f"Setting {key} = {value} for guild {guild_id}")
    await config_service.set_guild_setting(guild_id, key, value)

    print(f"Retrieving {key} for guild {guild_id}")
    retrieved = await config_service.get_guild_setting(guild_id, key)
    print(f"Retrieved: {retrieved}")

    # Also test guild settings cache
    print("Getting all guild settings...")
    all_settings = await config_service._get_guild_settings(guild_id)
    print(f"All settings: {all_settings}")


if __name__ == "__main__":
    asyncio.run(test_config_service())
