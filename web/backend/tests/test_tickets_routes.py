"""
Tests for ticket API endpoints (/api/tickets/).

Uses the ``client``, ``mock_admin_session``, and ``mock_discord_manager_session``
fixtures from the backend test conftest.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.contract


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_categories_empty(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Listing categories for a guild with none returns an empty list."""
    response = await client.get(
        "/api/tickets/categories",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["categories"] == []


@pytest.mark.asyncio
async def test_create_category(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Creating a category returns the updated category list."""
    payload = {
        "guild_id": "123",
        "name": "General",
        "description": "General support",
        "welcome_message": "Hi!",
        "role_ids": [],
        "allowed_statuses": ["bot_verified"],
        "emoji": "📩",
    }
    response = await client.post(
        "/api/tickets/categories",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert len(data["categories"]) == 1
    assert data["categories"][0]["name"] == "General"
    assert data["categories"][0]["allowed_statuses"] == ["bot_verified"]


@pytest.mark.asyncio
async def test_create_category_guild_mismatch(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Creating a category for a different guild returns 403."""
    payload = {
        "guild_id": "999",  # does not match active guild 123
        "name": "Nope",
    }
    response = await client.post(
        "/api/tickets/categories",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_category(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Updating a category changes its fields."""
    # Create first
    create_resp = await client.post(
        "/api/tickets/categories",
        json={"guild_id": "123", "name": "Old"},
        cookies={"session": mock_admin_session},
    )
    cat_id = create_resp.json()["categories"][0]["id"]

    # Update
    update_resp = await client.put(
        f"/api/tickets/categories/{cat_id}",
        json={"name": "New"},
        cookies={"session": mock_admin_session},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["success"] is True


@pytest.mark.asyncio
async def test_create_category_invalid_allowed_statuses(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Invalid eligibility status values are rejected by schema validation."""
    payload = {
        "guild_id": "123",
        "name": "General",
        "allowed_statuses": ["invalid_status"],
    }
    response = await client.post(
        "/api/tickets/categories",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_category_not_found(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Updating a non-existent category returns 404."""
    response = await client.put(
        "/api/tickets/categories/99999",
        json={"name": "X"},
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_category(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Deleting a category returns success."""
    create_resp = await client.post(
        "/api/tickets/categories",
        json={"guild_id": "123", "name": "ToDelete"},
        cookies={"session": mock_admin_session},
    )
    cat_id = create_resp.json()["categories"][-1]["id"]

    delete_resp = await client.delete(
        f"/api/tickets/categories/{cat_id}",
        cookies={"session": mock_admin_session},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True


@pytest.mark.asyncio
async def test_delete_category_not_found(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Deleting a non-existent category returns 404."""
    response = await client.delete(
        "/api/tickets/categories/99999",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Channel Configs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_channel_config_with_public_button_fields(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Creating a channel config accepts optional public button fields."""
    response = await client.post(
        "/api/tickets/channels",
        json={
            "guild_id": "123",
            "channel_id": "456",
            "button_text": "Create Private Ticket",
            "enable_public_button": True,
            "public_button_text": "Create Public Ticket",
            "public_button_emoji": "🌍",
        },
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert len(data["channels"]) == 1
    channel_cfg = data["channels"][0]
    assert channel_cfg["enable_public_button"] is True
    assert channel_cfg["public_button_text"] == "Create Public Ticket"
    assert channel_cfg["public_button_emoji"] == "🌍"


@pytest.mark.asyncio
async def test_update_channel_config_public_button_fields(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Updating channel config can toggle public button settings."""
    create_resp = await client.post(
        "/api/tickets/channels",
        json={"guild_id": "123", "channel_id": "789"},
        cookies={"session": mock_discord_manager_session},
    )
    assert create_resp.status_code == 201

    update_resp = await client.put(
        "/api/tickets/channels/789",
        json={
            "enable_public_button": True,
            "public_button_text": "Open Public Ticket",
            "public_button_emoji": "🌐",
        },
        cookies={"session": mock_discord_manager_session},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["success"] is True

    list_resp = await client.get(
        "/api/tickets/channels",
        cookies={"session": mock_discord_manager_session},
    )
    channels = list_resp.json()["channels"]
    target = next((c for c in channels if c["channel_id"] == "789"), None)
    assert target is not None
    assert target["enable_public_button"] is True
    assert target["public_button_text"] == "Open Public Ticket"
    assert target["public_button_emoji"] == "🌐"


@pytest.mark.asyncio
async def test_create_channel_config_with_button_colors_and_order(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Creating a channel config accepts button color and order fields."""
    response = await client.post(
        "/api/tickets/channels",
        json={
            "guild_id": "123",
            "channel_id": "999",
            "enable_public_button": True,
            "private_button_color": "3BA55D",
            "public_button_color": "ED4245",
            "button_order": "public_first",
        },
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    channel_cfg = data["channels"][0]
    assert channel_cfg["private_button_color"] == "3BA55D"
    assert channel_cfg["public_button_color"] == "ED4245"
    assert channel_cfg["button_order"] == "public_first"


@pytest.mark.asyncio
async def test_update_channel_config_button_colors(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Updating channel config can modify button colors and order."""
    # Create config
    create_resp = await client.post(
        "/api/tickets/channels",
        json={
            "guild_id": "123",
            "channel_id": "888",
            "enable_public_button": True,
        },
        cookies={"session": mock_discord_manager_session},
    )
    assert create_resp.status_code == 201

    # Update colors and order
    update_resp = await client.put(
        "/api/tickets/channels/888",
        json={
            "private_button_color": "5865F2",
            "public_button_color": "4F545C",
            "button_order": "public_first",
        },
        cookies={"session": mock_discord_manager_session},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["success"] is True

    # Verify persistence
    list_resp = await client.get(
        "/api/tickets/channels",
        cookies={"session": mock_discord_manager_session},
    )
    channels = list_resp.json()["channels"]
    target = next((c for c in channels if c["channel_id"] == "888"), None)
    assert target is not None
    assert target["private_button_color"] == "5865F2"
    assert target["public_button_color"] == "4F545C"
    assert target["button_order"] == "public_first"


# ---------------------------------------------------------------------------
# Tickets list & stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tickets_empty(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Listing tickets when none exist returns empty list."""
    response = await client.get(
        "/api/tickets/list",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_ticket_stats_empty(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Stats with no tickets shows zeroes."""
    response = await client.get(
        "/api/tickets/stats",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["open"] == 0
    assert data["closed"] == 0
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_default(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Getting settings when nothing is configured returns defaults."""
    response = await client.get(
        "/api/tickets/settings",
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "settings" in data


@pytest.mark.asyncio
async def test_update_settings(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Updating settings stores the values."""
    payload = {
        "channel_id": "111222333",
        "close_message": "Thanks!",
    }
    response = await client.put(
        "/api/tickets/settings",
        json=payload,
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Verify persisted
    get_resp = await client.get(
        "/api/tickets/settings",
        cookies={"session": mock_discord_manager_session},
    )
    settings = get_resp.json()["settings"]
    assert settings["channel_id"] == "111222333"
    assert settings["close_message"] == "Thanks!"


@pytest.mark.asyncio
async def test_update_settings_rejects_deprecated_panel_fields(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Deprecated global panel fields should be rejected."""
    response = await client.put(
        "/api/tickets/settings",
        json={"panel_title": "Legacy title"},
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Deploy panel (mocked — internal API is not available in tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_panel_triggers_internal_api(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """deploy-panel should call the internal API and return the result."""
    response = await client.post(
        "/api/tickets/deploy-panel",
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message_id"] is not None


@pytest.mark.asyncio
async def test_deploy_panel_propagates_internal_api_error(
    client: AsyncClient,
    mock_discord_manager_session: str,
    fake_internal_api,
) -> None:
    """deploy-panel should preserve upstream HTTP status/detail from internal API."""

    async def _raise_upstream_error(
        guild_id: int, *, channel_id: str | None = None,
    ) -> dict:
        request = httpx.Request(
            "POST", f"http://127.0.0.1:8082/guilds/{guild_id}/tickets/deploy-panel"
        )
        response = httpx.Response(
            status_code=503,
            request=request,
            json={"detail": "Bot internal API is warming up"},
        )
        raise httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=request,
            response=response,
        )

    fake_internal_api.deploy_ticket_panel = _raise_upstream_error

    response = await client.post(
        "/api/tickets/deploy-panel",
        cookies={"session": mock_discord_manager_session},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Bot internal API is warming up"


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_categories_require_auth(client: AsyncClient) -> None:
    """Unauthenticated requests should be rejected."""
    response = await client.get("/api/tickets/categories")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_settings_require_discord_manager(
    client: AsyncClient, mock_moderator_session: str
) -> None:
    """Moderators should not be able to update settings (requires discord_manager)."""
    response = await client.put(
        "/api/tickets/settings",
        json={"close_message": "Nope"},
        cookies={"session": mock_moderator_session},
    )
    assert response.status_code == 403
