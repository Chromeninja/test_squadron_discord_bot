"""
Tests for voice channel search endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_voice_search_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """Test voice search rejects unauthorized users."""
    response = await client.get(
        "/api/voice/search?user_id=123456789",
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_voice_search_by_user_id(client: AsyncClient, mock_admin_session: str):
    """Test searching voice channels by user ID."""
    response = await client.get(
        "/api/voice/search?user_id=123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Check first item
    item = data["items"][0]
    assert item["owner_id"] == 123456789
    assert "voice_channel_id" in item
    assert "is_active" in item


@pytest.mark.asyncio
async def test_voice_search_no_results(client: AsyncClient, mock_admin_session: str):
    """Test voice search with no results."""
    response = await client.get(
        "/api/voice/search?user_id=999999999",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 0
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_voice_search_moderator(client: AsyncClient, mock_moderator_session: str):
    """Test voice search works for moderators."""
    response = await client.get(
        "/api/voice/search?user_id=987654321",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1


# Tests for /api/voice/user-settings endpoint


@pytest.mark.asyncio
async def test_user_settings_search_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """Test user settings search rejects unauthorized users."""
    response = await client.get(
        "/api/voice/user-settings?query=TestUser1",
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_settings_search_by_discord_id(
    client: AsyncClient, mock_admin_session: str, temp_db: str
):
    """Test searching user settings by exact Discord ID."""
    # Add test JTC settings for user
    from services.db.database import Database

    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT INTO channel_settings
            (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
            VALUES (123, 2222, 123456789, 'Test Channel', 5, 1)
            """
        )
        await db.execute(
            """
            INSERT INTO user_jtc_preferences
            (guild_id, user_id, last_used_jtc_channel_id)
            VALUES (123, 123456789, 2222)
            """
        )
        await db.commit()

    response = await client.get(
        "/api/voice/user-settings?query=123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 1

    user = data["items"][0]
    assert user["user_id"] == "123456789"  # String for snowflake precision
    assert user["rsi_handle"] == "TestUser1"
    assert user["primary_jtc_id"] == "2222"  # String for snowflake precision
    assert len(user["jtcs"]) == 1

    jtc = user["jtcs"][0]
    assert jtc["jtc_channel_id"] == "2222"  # String for snowflake precision
    assert jtc["channel_name"] == "Test Channel"
    assert jtc["user_limit"] == 5
    assert jtc["lock"] is True
    # Ensure arrays are present (even if empty)
    assert isinstance(jtc["permissions"], list)
    assert isinstance(jtc["ptt_settings"], list)
    assert isinstance(jtc["priority_settings"], list)
    assert isinstance(jtc["soundboard_settings"], list)


@pytest.mark.asyncio
async def test_user_settings_search_by_rsi_handle_partial(
    client: AsyncClient, mock_admin_session: str, temp_db: str
):
    """Test searching user settings by partial RSI handle match (multiple results)."""
    # Add test JTC settings for multiple users
    from services.db.database import Database

    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT INTO channel_settings
            (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
            VALUES
                (123, 2222, 123456789, 'User1 Channel', 5, 0),
                (123, 2223, 987654321, 'User2 Channel', 10, 1)
            """
        )
        await db.commit()

    # Search for "TestUser" which should match all 4 TestUser* entries in verification
    response = await client.get(
        "/api/voice/user-settings?query=TestUser",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 4  # TestUser1, TestUser2, TestUser3, TestUser4
    assert len(data["items"]) == 4

    # Users with settings we added should be returned (IDs as strings for snowflake precision)
    user_ids = {item["user_id"] for item in data["items"]}
    assert "123456789" in user_ids
    assert "987654321" in user_ids


@pytest.mark.asyncio
async def test_user_settings_search_no_results(
    client: AsyncClient, mock_admin_session: str
):
    """Test user settings search with no matching users."""
    response = await client.get(
        "/api/voice/user-settings?query=NonExistentUser",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 0
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_user_settings_search_user_exists_no_settings(
    client: AsyncClient, mock_admin_session: str
):
    """Test user found but has no JTC settings in current guild."""
    # User 111222333 exists in verification but has no settings
    response = await client.get(
        "/api/voice/user-settings?query=111222333",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1
    assert len(data["items"]) == 1

    user = data["items"][0]
    assert user["user_id"] == "111222333"  # String for snowflake precision
    assert user["rsi_handle"] == "TestUser3"
    assert user["primary_jtc_id"] is None
    assert user["jtcs"] == []  # Empty list, not null


@pytest.mark.asyncio
async def test_user_settings_search_multiple_jtc_channels(
    client: AsyncClient, mock_admin_session: str, temp_db: str
):
    """Test user with settings in multiple JTC channels."""
    from services.db.database import Database

    async with Database.get_connection() as db:
        # Add settings for multiple JTCs
        await db.execute(
            """
            INSERT INTO channel_settings
            (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
            VALUES
                (123, 2222, 123456789, 'JTC A', 5, 0),
                (123, 3333, 123456789, 'JTC B', 10, 1),
                (123, 4444, 123456789, 'JTC C', 0, 0)
            """
        )
        # Set primary JTC
        await db.execute(
            """
            INSERT INTO user_jtc_preferences
            (guild_id, user_id, last_used_jtc_channel_id)
            VALUES (123, 123456789, 3333)
            """
        )
        # Add some permissions to one JTC
        await db.execute(
            """
            INSERT INTO channel_permissions
            (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
            VALUES (123, 2222, 123456789, 555, 'role', 'connect')
            """
        )
        await db.commit()

    response = await client.get(
        "/api/voice/user-settings?query=123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    user = data["items"][0]
    assert user["primary_jtc_id"] == "3333"  # String for snowflake precision
    assert len(user["jtcs"]) == 3

    # Check JTC IDs are present (as strings)
    jtc_ids = {jtc["jtc_channel_id"] for jtc in user["jtcs"]}
    assert jtc_ids == {"2222", "3333", "4444"}

    # Find JTC with permissions
    jtc_with_perms = next(
        (j for j in user["jtcs"] if j["jtc_channel_id"] == "2222"), None
    )
    assert jtc_with_perms is not None
    assert len(jtc_with_perms["permissions"]) == 1
    perm = jtc_with_perms["permissions"][0]
    assert perm["target_id"] == "555"  # String for snowflake precision
    assert perm["target_type"] == "role"
    assert perm["permission"] == "connect"


@pytest.mark.asyncio
async def test_user_settings_search_pagination(
    client: AsyncClient, mock_admin_session: str
):
    """Test pagination of user settings search results."""
    # Search with page_size=1 - should find all 4 TestUser* entries
    response = await client.get(
        "/api/voice/user-settings?query=TestUser&page=1&page_size=1",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 4  # TestUser1, TestUser2, TestUser3, TestUser4
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert len(data["items"]) == 1

    # Get page 2
    response = await client.get(
        "/api/voice/user-settings?query=TestUser&page=2&page_size=1",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 4
    assert data["page"] == 2
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_user_settings_search_guild_scoping(
    client: AsyncClient, mock_admin_session: str, temp_db: str
):
    """Test that settings are properly scoped to the active guild."""
    from services.db.database import Database

    async with Database.get_connection() as db:
        # Add settings in guild 123 (active guild for admin)
        await db.execute(
            """
            INSERT INTO channel_settings
            (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
            VALUES (123, 2222, 123456789, 'Guild 123 Channel', 5, 0)
            """
        )
        # Add settings in different guild 456
        await db.execute(
            """
            INSERT INTO channel_settings
            (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
            VALUES (456, 7777, 123456789, 'Guild 456 Channel', 10, 1)
            """
        )
        await db.commit()

    # Search should only return settings for guild 123
    response = await client.get(
        "/api/voice/user-settings?query=123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    user = data["items"][0]
    assert len(user["jtcs"]) == 1
    assert user["jtcs"][0]["jtc_channel_id"] == "2222"  # String for snowflake precision
    assert user["jtcs"][0]["channel_name"] == "Guild 123 Channel"
    # Settings from guild 456 should NOT be included


@pytest.mark.asyncio
async def test_user_settings_search_all_setting_types(
    client: AsyncClient, mock_admin_session: str, temp_db: str
):
    """Test that all setting types (permissions, PTT, priority, soundboard) are returned."""
    from services.db.database import Database

    async with Database.get_connection() as db:
        # Add basic settings
        await db.execute(
            """
            INSERT INTO channel_settings
            (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
            VALUES (123, 2222, 123456789, 'Full Settings Channel', 5, 0)
            """
        )
        # Add permissions
        await db.execute(
            """
            INSERT INTO channel_permissions
            (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
            VALUES (123, 2222, 123456789, 111, 'user', 'speak')
            """
        )
        # Add PTT settings
        await db.execute(
            """
            INSERT INTO channel_ptt_settings
            (guild_id, jtc_channel_id, user_id, target_id, target_type, ptt_enabled)
            VALUES (123, 2222, 123456789, 222, 'role', 1)
            """
        )
        # Add priority speaker settings
        await db.execute(
            """
            INSERT INTO channel_priority_speaker_settings
            (guild_id, jtc_channel_id, user_id, target_id, target_type, priority_enabled)
            VALUES (123, 2222, 123456789, 333, 'user', 0)
            """
        )
        # Add soundboard settings
        await db.execute(
            """
            INSERT INTO channel_soundboard_settings
            (guild_id, jtc_channel_id, user_id, target_id, target_type, soundboard_enabled)
            VALUES (123, 2222, 123456789, 444, 'role', 1)
            """
        )
        await db.commit()

    response = await client.get(
        "/api/voice/user-settings?query=123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    jtc = data["items"][0]["jtcs"][0]

    # Check permissions
    assert len(jtc["permissions"]) == 1
    assert jtc["permissions"][0]["target_id"] == "111"  # String for snowflake precision
    assert jtc["permissions"][0]["target_type"] == "user"
    assert jtc["permissions"][0]["permission"] == "speak"

    # Check PTT settings
    assert len(jtc["ptt_settings"]) == 1
    assert (
        jtc["ptt_settings"][0]["target_id"] == "222"
    )  # String for snowflake precision
    assert jtc["ptt_settings"][0]["ptt_enabled"] is True

    # Check priority speaker settings
    assert len(jtc["priority_settings"]) == 1
    assert (
        jtc["priority_settings"][0]["target_id"] == "333"
    )  # String for snowflake precision
    assert jtc["priority_settings"][0]["priority_enabled"] is False

    # Check soundboard settings
    assert len(jtc["soundboard_settings"]) == 1
    assert (
        jtc["soundboard_settings"][0]["target_id"] == "444"
    )  # String for snowflake precision
    assert jtc["soundboard_settings"][0]["soundboard_enabled"] is True


@pytest.mark.asyncio
async def test_user_settings_search_moderator_access(
    client: AsyncClient, mock_moderator_session: str
):
    """Test that moderators can access user settings search."""
    response = await client.get(
        "/api/voice/user-settings?query=TestUser1",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
