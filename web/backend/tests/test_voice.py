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
async def test_voice_search_moderator(
    client: AsyncClient, mock_moderator_session: str
):
    """Test voice search works for moderators."""
    response = await client.get(
        "/api/voice/search?user_id=987654321",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 1
