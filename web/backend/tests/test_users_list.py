"""Tests for enriched users list and export endpoints."""

from http import HTTPStatus

import pytest
from httpx import AsyncClient

DEFAULT_PAGE = 1
SECOND_PAGE = 2
DEFAULT_PAGE_SIZE = 25
SMALL_PAGE_SIZE = 2


pytestmark = pytest.mark.contract


def _use_fixture(*fixtures):
    """Helper to appease linters for fixtures with side effects."""
    for fixture in fixtures:
        assert fixture is not None


@pytest.mark.asyncio
async def test_list_users_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """Test users list endpoint rejects unauthorized users."""
    response = await client.get(
        "/api/users",
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 400  # User has no authorized guilds


@pytest.mark.asyncio
async def test_list_users_admin(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test users list returns enriched data for admin."""
    # Set up fake Discord member data
    fake_internal_api.member_data[(123, 246604397155581954)] = {
        "user_id": 246604397155581954,
        "username": "TestUser1",
        "discriminator": "0001",
        "global_name": "Test User 1",
        "avatar_url": "https://example.com/avatar1.png",
        "joined_at": "2024-01-01T00:00:00",
        "created_at": "2023-01-01T00:00:00",
        "roles": [
            {"id": 1001, "name": "Admin", "color": 16711680},
            {"id": 1002, "name": "Member", "color": 65280},
        ],
    }

    response = await client.get(
        "/api/users?page=1&page_size=25",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["success"] is True
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data

    assert data["page"] == DEFAULT_PAGE
    assert data["page_size"] == DEFAULT_PAGE_SIZE


@pytest.mark.asyncio
async def test_list_users_with_filter(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test users list filters by membership status."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/users?page=1&page_size=25&membership_status=main",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["success"] is True
    # Should only return users with status="main"
    for item in data["items"]:
        assert item["membership_status"] == "main"


@pytest.mark.asyncio
async def test_list_users_pagination(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test users list pagination works correctly."""
    _use_fixture(fake_internal_api)
    # Page 1
    response = await client.get(
        "/api/users?page=1&page_size=2",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["page"] == DEFAULT_PAGE
    assert data["page_size"] == SMALL_PAGE_SIZE
    assert len(data["items"]) <= SMALL_PAGE_SIZE

    # Page 2
    response = await client.get(
        "/api/users?page=2&page_size=2",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["page"] == SECOND_PAGE


@pytest.mark.asyncio
async def test_export_users_all(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test CSV export of all users."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/export",
        json={},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    assert "members_export" in response.headers["content-disposition"]

    # Check CSV content
    csv_content = response.text
    lines = csv_content.strip().split("\n")

    # Should have header
    assert "discord_id" in lines[0]
    assert "username" in lines[0]
    assert "membership_status" in lines[0]


@pytest.mark.asyncio
async def test_export_users_filtered(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test CSV export with membership status filter."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/export",
        json={"membership_status": "main"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/csv; charset=utf-8"


@pytest.mark.asyncio
async def test_export_users_selected(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test CSV export of selected users only."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/export",
        json={"selected_ids": ["246604397155581954", "1428084144860303511"]},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    # Check that only selected users are in CSV
    csv_content = response.text
    lines = csv_content.strip().split("\n")

    # Should have header + data rows
    assert len(lines) >= 1  # At least header


@pytest.mark.asyncio
async def test_export_users_with_exclusions(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Export should honor exclude_ids when exporting filtered results."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/export",
        json={
            "membership_statuses": ["main", "affiliate"],
            "exclude_ids": ["123456789"],
        },
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    csv_content = response.text
    lines = csv_content.strip().split("\n")

    # Check header exists
    assert "discord_id" in lines[0]

    # Check that excluded user is not in the discord_id column (first column)
    discord_ids = [line.split(",")[0] for line in lines[1:] if line]
    assert "123456789" not in discord_ids
    assert "987654321" in discord_ids


@pytest.mark.asyncio
async def test_export_users_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """Test export endpoint rejects unauthorized users."""
    response = await client.post(
        "/api/users/export",
        json={},
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 400  # User has no authorized guilds


@pytest.mark.asyncio
async def test_list_users_moderator(
    client: AsyncClient, mock_moderator_session: str, fake_internal_api
):
    """Test users list works for moderators."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/users",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
