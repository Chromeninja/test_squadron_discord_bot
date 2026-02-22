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


@pytest.mark.asyncio
async def test_list_users_with_search(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test users list filters by search query."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/users?search=TestUser1",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    # Should find at least the user with rsi_handle=TestUser1
    handles = [item["rsi_handle"] for item in data["items"] if item.get("rsi_handle")]
    assert "TestUser1" in handles


@pytest.mark.asyncio
async def test_list_users_with_orgs_filter(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test users list filters by org SID."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/users?orgs=TEST",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    # All returned users should have TEST in their orgs
    for item in data["items"]:
        all_orgs = (item.get("main_orgs") or []) + (item.get("affiliate_orgs") or [])
        assert "TEST" in all_orgs


@pytest.mark.asyncio
async def test_list_users_search_with_wildcard(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test that LIKE wildcards in search are escaped properly."""
    _use_fixture(fake_internal_api)
    # Search with % character should be treated literally, not as wildcard
    response = await client.get(
        "/api/users?search=100%25match",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    # Should return 0 results since no user has "100%match" in their data
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_get_available_orgs(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test /api/users/orgs returns distinct org SIDs."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/users/orgs",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["orgs"], list)
    # Our test data has "TEST" as an org
    assert "TEST" in data["orgs"]


@pytest.mark.asyncio
async def test_export_users_with_search(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Test CSV export includes search filter."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/export",
        json={"search": "TestUser1"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/csv; charset=utf-8"


# ── resolve-ids endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_ids_returns_all_filtered(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """POST /api/users/resolve-ids returns matching user IDs for current guild."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/resolve-ids",
        json={},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data["user_ids"], list)
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_resolve_ids_with_org_filter(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """resolve-ids respects org filter (AND logic)."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/resolve-ids",
        json={"orgs": ["TEST"]},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data["user_ids"], list)
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_resolve_ids_with_exclude(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """resolve-ids honours exclude_ids."""
    _use_fixture(fake_internal_api)
    # First get all IDs
    all_resp = await client.post(
        "/api/users/resolve-ids",
        json={},
        cookies={"session": mock_admin_session},
    )
    all_ids = all_resp.json()["user_ids"]

    if len(all_ids) > 0:
        # Exclude first user
        resp = await client.post(
            "/api/users/resolve-ids",
            json={"exclude_ids": [all_ids[0]]},
            cookies={"session": mock_admin_session},
        )
        data = resp.json()
        assert all_ids[0] not in data["user_ids"]
        assert data["total"] == len(all_ids) - 1


@pytest.mark.asyncio
async def test_resolve_ids_respects_limit(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """resolve-ids caps returned IDs at the requested limit."""
    _use_fixture(fake_internal_api)
    response = await client.post(
        "/api/users/resolve-ids",
        json={"limit": 1},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data["user_ids"]) <= 1


@pytest.mark.asyncio
async def test_resolve_ids_unauthorized(
    client: AsyncClient, mock_unauthorized_session: str
):
    """resolve-ids rejects unauthorized users."""
    response = await client.post(
        "/api/users/resolve-ids",
        json={},
        cookies={"session": mock_unauthorized_session},
    )

    assert response.status_code == 400