"""
Tests for authentication endpoints.
"""

import pytest
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
