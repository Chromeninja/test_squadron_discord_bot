"""
Tests for new-member role settings backend endpoints.

Covers:
- GET/PUT /api/guilds/{guild_id}/settings/new-member-role
- Default values when no settings exist
- Round-trip persistence
- Settings version bump on save
"""

import pytest
from core.security import create_session_token_async
from httpx import AsyncClient

pytestmark = pytest.mark.contract


async def _admin_session(guild_id: int = 123) -> str:
    """Create an admin session token for a test guild."""
    return await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": str(guild_id),
            "authorized_guilds": {
                str(guild_id): {
                    "guild_id": str(guild_id),
                    "role_level": "bot_admin",
                    "source": "bot_owner",
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_get_new_member_role_defaults(
    client: AsyncClient, mock_admin_session: str
):
    """When no settings exist, return sensible defaults."""
    response = await client.get(
        "/api/guilds/123/settings/new-member-role",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["role_id"] is None
    assert data["duration_days"] == 14
    assert data["max_server_age_days"] is None


@pytest.mark.asyncio
async def test_put_new_member_role_persists(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """PUT should persist new-member role settings."""
    payload = {
        "enabled": True,
        "role_id": "999111222",
        "duration_days": 30,
        "max_server_age_days": 7,
    }
    response = await client.put(
        "/api/guilds/123/settings/new-member-role",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["role_id"] == "999111222"
    assert data["duration_days"] == 30
    assert data["max_server_age_days"] == 7

    # Verify internal API refresh notification
    assert fake_internal_api.refresh_calls
    assert fake_internal_api.refresh_calls[-1]["source"] == "new_member_role"


@pytest.mark.asyncio
async def test_put_new_member_role_roundtrip(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Values persisted by PUT should be returned by subsequent GET."""
    payload = {
        "enabled": True,
        "role_id": "888777666",
        "duration_days": 7,
        "max_server_age_days": None,
    }
    await client.put(
        "/api/guilds/123/settings/new-member-role",
        json=payload,
        cookies={"session": mock_admin_session},
    )

    response = await client.get(
        "/api/guilds/123/settings/new-member-role",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["role_id"] == "888777666"
    assert data["duration_days"] == 7
    assert data["max_server_age_days"] is None


@pytest.mark.asyncio
async def test_put_new_member_role_disabled(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Disabling the module should persist correctly."""
    # First enable
    await client.put(
        "/api/guilds/123/settings/new-member-role",
        json={"enabled": True, "role_id": "111", "duration_days": 5},
        cookies={"session": mock_admin_session},
    )

    # Then disable
    response = await client.put(
        "/api/guilds/123/settings/new-member-role",
        json={"enabled": False, "role_id": "111", "duration_days": 5},
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


@pytest.mark.asyncio
async def test_put_duration_days_minimum(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """duration_days should be at least 1."""
    payload = {
        "enabled": True,
        "role_id": "555",
        "duration_days": 0,  # below minimum
    }
    response = await client.put(
        "/api/guilds/123/settings/new-member-role",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    # Pydantic ge=1 validation should reject 0
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_new_member_role_fresh_guild(
    client: AsyncClient,
):
    """GET on a guild with no seeded data returns defaults."""
    session_777 = await _admin_session(guild_id=777)
    response = await client.get(
        "/api/guilds/777/settings/new-member-role",
        cookies={"session": session_777},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["role_id"] is None


@pytest.mark.asyncio
async def test_put_max_server_age_days_zero_rejected(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """max_server_age_days=0 should be rejected by Pydantic ge=1 validation."""
    payload = {
        "enabled": True,
        "role_id": "555",
        "duration_days": 7,
        "max_server_age_days": 0,
    }
    response = await client.put(
        "/api/guilds/123/settings/new-member-role",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_enabled_requires_role_id(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """enabled=True should require a non-null role_id."""
    payload = {
        "enabled": True,
        "role_id": None,
        "duration_days": 7,
        "max_server_age_days": None,
    }
    response = await client.put(
        "/api/guilds/123/settings/new-member-role",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 422
