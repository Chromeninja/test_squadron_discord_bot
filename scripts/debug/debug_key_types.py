"""Test both flat and nested key functionality.

Developer utility moved into scripts/debug/.
"""

import asyncio
import tempfile

from services.config_service import ConfigService
from services.db.database import Database


async def test_both_key_types():
    """Test both flat and nested keys."""
    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    await Database.initialize(db_path)

    config_service = ConfigService()
    await config_service.initialize()

    # Set global config after initialization
    config_service._global_config = {"roles": {"admin": 123456}}

    guild_id = 12345

    # Test flat key
    print("Testing flat key...")
    await config_service.set_guild_setting(
        guild_id, "test.setting", {"nested": "value"}
    )
    retrieved_flat = await config_service.get_guild_setting(guild_id, "test.setting")
    print(f"Flat key result: {retrieved_flat}")

    # Test nested key access from global config
    print("Testing nested key from global config...")
    retrieved_nested = await config_service.get_guild_setting(
        guild_id, "roles.admin", default="not found"
    )
    print(f"Nested key result: {retrieved_nested}")

    # Test global setting method directly
    print("Testing global setting method...")
    global_nested = await config_service.get_global_setting(
        "roles.admin", default="not found"
    )
    print(f"Global setting result: {global_nested}")


if __name__ == "__main__":
    asyncio.run(test_both_key_types())
