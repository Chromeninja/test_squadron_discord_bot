"""Tests for guild settings and member endpoints."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from core.security import create_session_token
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_bot_role_settings_defaults(
    client: AsyncClient, mock_admin_session: str
):
    """When no settings exist, all role arrays should be empty."""
    response = await client.get(
        "/api/guilds/123/settings/bot-roles",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["bot_admins"] == []
    assert data["lead_moderators"] == []
    assert data["main_role"] == []
    assert data["affiliate_role"] == []
    assert data["nonmember_role"] == []


@pytest.mark.asyncio
async def test_put_bot_role_settings_persists_values(
    client: AsyncClient, mock_admin_session: str
):
    """PUT should normalize and persist role IDs for all categories."""
    payload = {
        "bot_admins": [5, 5, 2],
        "lead_moderators": [8],
        "main_role": [10],
        "affiliate_role": [11, 12],
        "nonmember_role": [13],
    }

    response = await client.put(
        "/api/guilds/123/settings/bot-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["bot_admins"] == [2, 5]
    assert data["lead_moderators"] == [8]
    assert data["main_role"] == [10]
    assert data["affiliate_role"] == [11, 12]
    assert data["nonmember_role"] == [13]

    # Subsequent GET should match persisted data
    follow_up = await client.get(
        "/api/guilds/123/settings/bot-roles",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    persisted = follow_up.json()
    assert persisted == data


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
    payload = {"selectable_roles": [9, 2, 9, 5]}

    response = await client.put(
        "/api/guilds/123/settings/voice/selectable-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["selectable_roles"] == [2, 5, 9]

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
):
    """HTTP errors from the internal API should propagate status and detail."""
    error_response = httpx.Response(
        404,
        request=httpx.Request("GET", "http://internal"),
        content=json.dumps({"detail": "Member not found"}).encode(),
    )

    with patch(
        "core.dependencies.InternalAPIClient.get_guild_member",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "not found",
            request=error_response.request,
            response=error_response,
        )

        response = await client.get(
            "/api/guilds/123/members/999",
            cookies={"session": mock_admin_session},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Member not found"
