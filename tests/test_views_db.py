import pytest

from helpers.voice_utils import set_voice_feature_setting
from helpers.permissions_helper import store_permit_reject_in_db
from helpers.database import Database


@pytest.mark.asyncio
async def test_set_feature_and_permissions_scoped(temp_db):
    # Use the temp_db fixture to ensure Database is initialized to a temp file
    guild_id = 111222333
    jtc_id = 444555666
    owner_id = 1000

    # Set a feature (soundboard) for everyone scoped to guild/jtc
    await set_voice_feature_setting(
        "soundboard",
        owner_id,
        0,
        "everyone",
        True,
        guild_id=guild_id,
        jtc_channel_id=jtc_id,
    )

    # Store a permit entry for a user scoped to guild/jtc
    await store_permit_reject_in_db(owner_id, 2000, "user", "permit", guild_id=guild_id, jtc_channel_id=jtc_id)

    # Query underlying tables to ensure rows include guild_id and jtc_channel_id
    async with Database.get_connection() as db:
        cur = await db.execute("SELECT guild_id, jtc_channel_id, target_id, target_type, soundboard_enabled FROM channel_soundboard_settings WHERE user_id = ?", (owner_id,))
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == guild_id
        assert row[1] == jtc_id
        assert row[2] == 0
        assert row[3] == "everyone"
        assert row[4] == 1 or row[4] is True

        cur2 = await db.execute("SELECT guild_id, jtc_channel_id, target_id, target_type, permission FROM channel_permissions WHERE user_id = ?", (owner_id,))
        prow = await cur2.fetchone()
        assert prow is not None
        assert prow[0] == guild_id
        assert prow[1] == jtc_id
        assert prow[2] == 2000
        assert prow[3] == "user"
    assert prow[4] == "permit"
