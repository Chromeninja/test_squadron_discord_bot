import json

import pytest

from services.config_service import SETTINGS_VERSION_KEY, ConfigService
from services.db.database import Database


@pytest.mark.asyncio
async def test_maybe_refresh_guild_detects_version_change(temp_db):
    service = ConfigService()
    await service.initialize()

    guild_id = 321
    first_version = {"version": "v1"}
    second_version = {"version": "v2"}

    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            """,
            (guild_id, "roles.main_role", json.dumps(["1"])),
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            """,
            (guild_id, SETTINGS_VERSION_KEY, json.dumps(first_version)),
        )
        await db.commit()

    # Prime cache
    value = await service.get_guild_setting(guild_id, "roles.main_role", [])
    assert value == ["1"]

    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            """,
            (guild_id, SETTINGS_VERSION_KEY, json.dumps(second_version)),
        )
        await db.commit()

    refreshed = await service.maybe_refresh_guild(guild_id)
    assert refreshed is True
    assert service._guild_versions[guild_id] == "v2"

    await service.shutdown()


@pytest.mark.asyncio
async def test_maybe_refresh_guild_force_refreshes_without_version_change(temp_db):
    service = ConfigService()
    await service.initialize()

    guild_id = 654
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            """,
            (guild_id, SETTINGS_VERSION_KEY, json.dumps({"version": "same"})),
        )
        await db.commit()

    # Prime cache to store "same" version
    await service.get_guild_setting(guild_id, "roles.main_role", [])

    refreshed = await service.maybe_refresh_guild(guild_id, force=True)
    assert refreshed is True
    assert service._guild_versions[guild_id] == "same"

    await service.shutdown()
