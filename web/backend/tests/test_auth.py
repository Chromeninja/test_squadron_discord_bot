"""
Tests for authentication endpoints.
"""

import pytest
from core.security import decode_session_token
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_me_no_session(client: AsyncClient):
    """Test /api/auth/me without session returns null user."""
    response = await client.get("/api/auth/me")

    # Should succeed but user should be None
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is None


@pytest.mark.asyncio
async def test_auth_me_with_admin_session(client: AsyncClient, mock_admin_session: str):
    """Test /api/auth/me with valid admin session."""
    response = await client.get(
        "/api/auth/me",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is not None
    assert data["user"]["is_admin"] is True
    assert data["user"]["user_id"] == "246604397155581954"


@pytest.mark.asyncio
async def test_auth_me_with_moderator_session(
    client: AsyncClient, mock_moderator_session: str
):
    """Test /api/auth/me with valid moderator session."""
    response = await client.get(
        "/api/auth/me",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is not None
    assert data["user"]["is_moderator"] is True
    assert data["user"]["user_id"] == "1428084144860303511"


@pytest.mark.asyncio
async def test_login_redirect(client: AsyncClient):
    """Test /auth/login redirects to Discord."""
    response = await client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307  # Redirect
    assert "discord.com" in response.headers["location"]
    assert "oauth2/authorize" in response.headers["location"]


@pytest.mark.asyncio
async def test_get_guilds_returns_active_list(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Ensure /api/auth/guilds proxies through the internal API client."""
    fake_internal_api.guilds = [
        {"guild_id": 1, "guild_name": "Alpha", "icon_url": "https://example.com/a.png"},
        {"guild_id": 2, "guild_name": "Bravo", "icon_url": None},
    ]

    response = await client.get(
        "/api/auth/guilds",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["guilds"]) == 2
    assert data["guilds"][0]["guild_name"] == "Alpha"


@pytest.mark.asyncio
async def test_select_guild_sets_session_cookie(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Selecting a guild should update the session cookie with the guild ID."""
    fake_internal_api.guilds = [
        {"guild_id": 123, "guild_name": "Alpha", "icon_url": None},
    ]

    response = await client.post(
        "/api/auth/select-guild",
    json={"guild_id": "123"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    new_session = response.cookies.get("session")
    assert new_session

    decoded = decode_session_token(new_session)
    assert decoded is not None
    assert decoded["active_guild_id"] == "123"


@pytest.mark.asyncio
async def test_select_guild_rejects_unknown_guild(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    fake_internal_api.guilds = [
        {"guild_id": 999, "guild_name": "Known", "icon_url": None},
    ]

    response = await client.post(
        "/api/auth/select-guild",
        json={"guild_id": "1000"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Guild not found"


@pytest.mark.asyncio
async def test_select_guild_allows_when_internal_api_empty(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    fake_internal_api.guilds = []

    response = await client.post(
        "/api/auth/select-guild",
        json={"guild_id": "321"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
