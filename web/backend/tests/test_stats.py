"""
Tests for statistics endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stats_overview_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """Test stats endpoint rejects unauthorized users."""
    response = await client.get(
        "/api/stats/overview",
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_stats_overview_admin(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test stats endpoint returns correct data for admin."""
    # Set guild member count in fake internal API
    # Guild ID 123 is from the mock admin session fixture
    fake_internal_api.guild_stats[123] = {
        "guild_id": 123,
        "member_count": 100,  # Total guild members
        "approximate_member_count": None
    }

    response = await client.get(
        "/api/stats/overview",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "data" in data

    stats = data["data"]
    assert stats["total_verified"] == 4  # From seed data
    assert stats["by_status"]["main"] == 1
    assert stats["by_status"]["affiliate"] == 1
    assert stats["by_status"]["non_member"] == 1
    # Unknown = total_guild_members - verified_members
    # = 100 - (1 main + 1 affiliate + 1 non_member) = 97
    assert stats["by_status"]["unknown"] == 97
    assert stats["voice_active_count"] == 2  # Two active channels


@pytest.mark.asyncio
async def test_stats_overview_moderator(
    client: AsyncClient, mock_moderator_session: str, fake_internal_api
):
    """Test stats endpoint works for moderators."""
    # Set guild member count in fake internal API
    fake_internal_api.guild_stats[123] = {
        "guild_id": 123,
        "member_count": 100,
        "approximate_member_count": None
    }

    response = await client.get(
        "/api/stats/overview",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
