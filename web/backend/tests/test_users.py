"""
Tests for user search endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_users_search_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """Test user search rejects unauthorized users."""
    response = await client.get(
        "/api/users/search",
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_users_search_all(client: AsyncClient, mock_admin_session: str):
    """Test searching all users."""
    response = await client.get(
        "/api/users/search?query=",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 4
    assert len(data["items"]) == 4
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_users_search_by_user_id(client: AsyncClient, mock_admin_session: str):
    """Test searching by exact user_id."""
    response = await client.get(
        "/api/users/search?query=123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["user_id"] == 123456789
    assert data["items"][0]["rsi_handle"] == "TestUser1"


@pytest.mark.asyncio
async def test_users_search_by_handle(client: AsyncClient, mock_admin_session: str):
    """Test searching by RSI handle."""
    response = await client.get(
        "/api/users/search?query=TestUser2",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1
    assert data["items"][0]["rsi_handle"] == "TestUser2"
    assert data["items"][0]["membership_status"] == "affiliate"


@pytest.mark.asyncio
async def test_users_search_by_moniker(client: AsyncClient, mock_admin_session: str):
    """Test searching by community moniker."""
    response = await client.get(
        "/api/users/search?query=Test%20Main",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1
    assert data["items"][0]["community_moniker"] == "Test Main"


@pytest.mark.asyncio
async def test_users_search_pagination(client: AsyncClient, mock_admin_session: str):
    """Test pagination works correctly."""
    response = await client.get(
        "/api/users/search?query=&page=1&page_size=2",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
