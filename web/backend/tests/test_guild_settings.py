"""Tests for guild settings and member endpoints."""

import json

import httpx
import pytest
from core.security import create_session_token
from httpx import AsyncClient

from services.db.database import Database

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_get_bot_role_settings_defaults(
    client: AsyncClient, mock_admin_session: str
):
    """When no settings exist, all role arrays should be empty."""
    # Use guild ID 888 which has no seeded data
    # First need to create a session for guild 888
    session_888 = create_session_token(
        {
            "user_id": "246604397155581954",
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "888",
            "authorized_guilds": {
                "888": {
                    "guild_id": "888",
                    "role_level": "bot_admin",
                    "source": "bot_owner",
                },
            },
        }
    )

    response = await client.get(
        "/api/guilds/888/settings/bot-roles",
        cookies={"session": session_888},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["bot_admins"] == []
    assert data["moderators"] == []
    assert data["main_role"] == []
    assert data["affiliate_role"] == []
    assert data["nonmember_role"] == []


@pytest.mark.asyncio
async def test_put_bot_role_settings_persists_values(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """PUT should normalize and persist role IDs for all categories."""
    # Use strings to preserve 64-bit Discord snowflake precision
    # Include 999111222 (the admin's current role) so validation passes on follow-up GET
    payload = {
        "bot_admins": ["999111222", "5", "5", "2"],
        "moderators": ["8"],
        "main_role": ["10"],
        "affiliate_role": ["11", "12"],
        "nonmember_role": ["13"],
    }

    response = await client.put(
        "/api/guilds/123/settings/bot-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    data = response.json()
    # Response should be sorted string role IDs
    assert data["bot_admins"] == ["2", "5", "999111222"]
    assert data["moderators"] == ["8"]
    assert data["main_role"] == ["10"]
    assert data["affiliate_role"] == ["11", "12"]
    assert data["nonmember_role"] == ["13"]

    # Subsequent GET should match persisted data
    follow_up = await client.get(
        "/api/guilds/123/settings/bot-roles",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    persisted = follow_up.json()
    assert persisted == data

    # Ensure bot was notified about the change
    assert fake_internal_api.refresh_calls
    assert fake_internal_api.refresh_calls[0]["guild_id"] == 123
    assert fake_internal_api.refresh_calls[0]["source"] == "bot_roles"


@pytest.mark.asyncio
async def test_put_bot_role_settings_updates_version_marker(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    payload = {
        "bot_admins": ["5"],
        "moderators": ["7"],
        "main_role": ["10"],
        "affiliate_role": [],
        "nonmember_role": [],
    }

    response = await client.put(
        "/api/guilds/123/settings/bot-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT value FROM guild_settings
            WHERE guild_id = ? AND key = ?
            """,
            (123, "meta.settings_version"),
        )
        row = await cursor.fetchone()

    assert row is not None
    serialized = row[0]
    payload = json.loads(serialized)
    assert payload["source"] == "bot_roles"
    assert "version" in payload


@pytest.mark.asyncio
async def test_get_voice_selectable_roles_defaults(
    client: AsyncClient, mock_admin_session: str
):
    response = await client.get(
        "/api/guilds/123/settings/voice/selectable-roles",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["selectable_roles"] == []


@pytest.mark.asyncio
async def test_put_voice_selectable_roles_persists_values(
    client: AsyncClient, mock_admin_session: str
):
    # Use strings to preserve 64-bit Discord snowflake precision
    payload = {"selectable_roles": ["9", "2", "9", "5"]}

    response = await client.put(
        "/api/guilds/123/settings/voice/selectable-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    data = response.json()
    # Response should be sorted, deduplicated string role IDs
    assert data["selectable_roles"] == ["2", "5", "9"]

    follow_up = await client.get(
        "/api/guilds/123/settings/voice/selectable-roles",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    assert follow_up.json() == data


@pytest.mark.asyncio
async def test_get_discord_roles_proxies_internal_api(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Ensure the discord roles endpoint returns data from the internal API."""
    fake_internal_api.roles_by_guild[123] = [
        {"id": 10, "name": "Captain", "color": 0xFF0000},
        {"id": 11, "name": "Officer", "color": 0x00FF00},
    ]

    response = await client.get(
        "/api/guilds/123/roles/discord",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["roles"]) == 2
    assert data["roles"][0]["name"] == "Captain"


@pytest.mark.asyncio
async def test_get_discord_roles_rejects_mismatched_guild(
    client: AsyncClient, mock_admin_session: str
):
    """Requesting a non-active guild should be forbidden."""
    response = await client.get(
        "/api/guilds/999/roles/discord",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_guild_members_proxies_internal_api(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Members endpoint should return paginated data from internal API."""
    fake_internal_api.members_by_guild[123] = [
        {
            "user_id": 111,
            "username": "Alpha",
            "discriminator": "0001",
            "global_name": "Alpha",
            "roles": [
                {"id": 5, "name": "Pilot", "color": 0x123456},
            ],
        }
    ]

    response = await client.get(
        "/api/guilds/123/members?page=1&page_size=50",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["members"][0]["user_id"] == 111
    assert data["members"][0]["roles"][0]["name"] == "Pilot"


    @pytest.mark.asyncio
    async def test_guild_config_read_only_uses_shared_loader(
        monkeypatch, tmp_path, client: AsyncClient, mock_admin_session: str
    ):
        custom_config = tmp_path / "custom-config.yaml"
        custom_config.write_text(
            """
    rsi:
      user_agent: CUSTOM-UA
    voice_debug_logging_enabled: true
    """,
            encoding="utf-8",
        )

        # Ensure ConfigLoader consumes the override before client fixture initializes
        monkeypatch.setenv("CONFIG_PATH", str(custom_config))

        response = await client.get(
            "/api/guilds/123/config", cookies={"session": mock_admin_session}
        )

        assert response.status_code == 200
        ro = response.json()["data"]["read_only"]
        assert ro["rsi"]["user_agent"] == "CUSTOM-UA"
        assert ro["voice_debug_logging_enabled"] is True


@pytest.mark.asyncio
async def test_list_guild_members_forbidden_without_matching_active_guild(
    client: AsyncClient,
):
    """Users cannot query a guild different from the selected active guild."""
    mismatch_session = create_session_token(
        {
            "user_id": "246604397155581954",
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "is_admin": True,
            "is_moderator": False,
            "active_guild_id": "999",
            "authorized_guilds": {
                "999": {
                    "guild_id": "999",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
                "123": {
                    "guild_id": "123",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
            },
        }
    )

    response = await client.get(
        "/api/guilds/123/members",
        cookies={"session": mismatch_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_guild_member_detail_success(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Single member endpoint returns normalized payload."""
    fake_internal_api.member_data[(123, 555)] = {
        "user_id": 555,
        "username": "Bravo",
        "discriminator": "1234",
        "global_name": "Bravo",
        "avatar_url": None,
        "roles": [],
    }

    response = await client.get(
        "/api/guilds/123/members/555",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["member"]["user_id"] == 555
    assert data["member"]["username"] == "Bravo"


@pytest.mark.asyncio
async def test_get_guild_member_detail_http_status_error(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """HTTP errors from the internal API should propagate status and detail."""
    error_response = httpx.Response(
        404,
        request=httpx.Request("GET", "http://internal"),
        content=json.dumps({"detail": "Member not found"}).encode(),
    )

    # Override get_guild_member to raise an exception ONLY for user 999
    # For the admin user (246604397155581954), return normal data for role validation
    original_get_guild_member = fake_internal_api.get_guild_member

    async def selective_raise_error(guild_id, user_id):
        if user_id == 999:
            raise httpx.HTTPStatusError(
                "not found",
                request=error_response.request,
                response=error_response,
            )
        # For role validation of admin user, return normal member data
        return await original_get_guild_member(guild_id, user_id)

    fake_internal_api.get_guild_member = selective_raise_error

    response = await client.get(
        "/api/guilds/123/members/999",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Member not found"
