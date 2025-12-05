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
    assert data["user"]["user_id"] == "246604397155581954"
    assert "authorized_guilds" in data["user"]
    assert "123" in data["user"]["authorized_guilds"]
    assert data["user"]["authorized_guilds"]["123"]["role_level"] == "bot_admin"


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
    assert data["user"]["user_id"] == "1428084144860303511"
    assert "authorized_guilds" in data["user"]
    assert "123" in data["user"]["authorized_guilds"]
    assert data["user"]["authorized_guilds"]["123"]["role_level"] == "moderator"


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


@pytest.mark.asyncio
async def test_callback_grants_access_to_guild_owner(client: AsyncClient, monkeypatch):
    """Test that guild owners are granted admin access even without configured roles."""
    from unittest.mock import AsyncMock, MagicMock

    # Mock OAuth token exchange
    async def mock_post(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    # Mock Discord API calls
    async def mock_get(url, *args, **kwargs):
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            # Return guilds where user is owner
            mock_response.json = lambda: [
                {
                    "id": "246486575137947648",
                    "name": "Test Guild",
                    "owner": True,  # User is guild owner
                    "permissions": "2147483647",  # All permissions
                }
            ]
        elif "/users/@me" in url:
            # Return user info
            mock_response.json = lambda: {
                "id": "123456789",
                "username": "TestOwner",
                "discriminator": "0001",
                "avatar": None,
            }

        return mock_response

    # Mock httpx client
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    response = await client.get(
        "/auth/callback",
        params={"code": "test_code"},
        follow_redirects=False,
    )

    # Should redirect successfully
    assert response.status_code == 307

    # Check session cookie
    session_cookie = response.cookies.get("session")
    assert session_cookie is not None

    from core.security import decode_session_token

    session_data = decode_session_token(session_cookie)
    assert session_data is not None
    # Check authorized_guilds structure
    assert "246486575137947648" in session_data["authorized_guilds"]
    guild_permission = session_data["authorized_guilds"]["246486575137947648"]
    assert (
        guild_permission["role_level"] == "bot_admin"
    )  # Guild owners get bot_admin level
    assert guild_permission["source"] == "discord_owner"


@pytest.mark.asyncio
async def test_callback_grants_access_to_administrator(
    client: AsyncClient, monkeypatch
):
    """Test that users with Discord administrator permission are granted admin access."""
    from unittest.mock import AsyncMock, MagicMock

    # Mock OAuth token exchange
    async def mock_post(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    # Mock Discord API calls
    async def mock_get(url, *args, **kwargs):
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            # Return guilds where user has administrator permission
            mock_response.json = lambda: [
                {
                    "id": "246486575137947648",
                    "name": "Test Guild",
                    "owner": False,
                    "permissions": "8",  # Administrator permission (0x8)
                }
            ]
        elif "/users/@me" in url:
            # Return user info
            mock_response.json = lambda: {
                "id": "987654321",
                "username": "TestAdmin",
                "discriminator": "0002",
                "avatar": None,
            }

        return mock_response

    # Mock httpx client
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    response = await client.get(
        "/auth/callback",
        params={"code": "test_code"},
        follow_redirects=False,
    )

    # Should redirect successfully
    assert response.status_code == 307

    # Check session cookie
    session_cookie = response.cookies.get("session")
    assert session_cookie is not None

    from core.security import decode_session_token

    session_data = decode_session_token(session_cookie)
    assert session_data is not None
    # Check authorized_guilds structure
    assert "246486575137947648" in session_data["authorized_guilds"]
    guild_permission = session_data["authorized_guilds"]["246486575137947648"]
    assert guild_permission["role_level"] == "bot_admin"
    assert guild_permission["source"] == "discord_administrator"


@pytest.mark.asyncio
async def test_callback_denies_access_without_permissions(
    client: AsyncClient, monkeypatch
):
    """Test that users without owner/admin/configured roles are denied access."""
    from unittest.mock import AsyncMock, MagicMock

    # Mock OAuth token exchange
    async def mock_post(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    # Mock Discord API calls
    async def mock_get(url, *args, **kwargs):
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            # Return guilds where user has no special permissions
            mock_response.json = lambda: [
                {
                    "id": "246486575137947648",
                    "name": "Test Guild",
                    "owner": False,
                    "permissions": "0",  # No permissions
                }
            ]
        elif "/users/@me/guilds/" in url and "/member" in url:
            # Return member with no configured roles
            mock_response.json = lambda: {
                "roles": [],  # No roles
            }
        elif "/users/@me" in url:
            # Return user info
            mock_response.json = lambda: {
                "id": "111222333",
                "username": "TestUser",
                "discriminator": "0003",
                "avatar": None,
            }

        return mock_response

    # Mock httpx client
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    response = await client.get(
        "/auth/callback",
        params={"code": "test_code"},
        follow_redirects=False,
    )

    # Should return 403 Access Denied
    assert response.status_code == 403
    assert "Access Denied" in response.text
