"""Tests for bot channel settings endpoints."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure we can import from backend
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from app import app
from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    initialize_services,
)
from core.security import create_session_token


@pytest_asyncio.fixture(autouse=True)
async def setup_teardown():
    """Initialize services before each test."""
    await initialize_services()
    yield


@pytest.fixture
def admin_user_token():
    """Create a session token for an admin user."""
    user_data = {
        "user_id": "12345",
        "username": "AdminUser",
        "discriminator": "0001",
        "avatar": None,
        "is_admin": True,
        "is_moderator": False,
        "active_guild_id": "123",
    }
    return create_session_token(user_data)


@pytest.mark.asyncio
async def test_get_bot_channel_settings_defaults(admin_user_token):
    """Test GET /api/guilds/{guild_id}/settings/bot-channels returns defaults."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/guilds/123/settings/bot-channels",
            cookies={"session": admin_user_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["verification_channel_id"] is None
    assert data["bot_spam_channel_id"] is None
    assert data["public_announcement_channel_id"] is None
    assert data["leadership_announcement_channel_id"] is None


@pytest.mark.asyncio
async def test_put_bot_channel_settings_persists_values(admin_user_token):
    """Test PUT /api/guilds/{guild_id}/settings/bot-channels persists values."""
    payload = {
        "verification_channel_id": 1111,
        "bot_spam_channel_id": 2222,
        "public_announcement_channel_id": 3333,
        "leadership_announcement_channel_id": 4444,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # PUT new settings
        put_response = await client.put(
            "/api/guilds/123/settings/bot-channels",
            json=payload,
            cookies={"session": admin_user_token},
        )
        assert put_response.status_code == 200
        put_data = put_response.json()
        assert put_data["verification_channel_id"] == 1111
        assert put_data["bot_spam_channel_id"] == 2222
        assert put_data["public_announcement_channel_id"] == 3333
        assert put_data["leadership_announcement_channel_id"] == 4444

        # GET to verify persistence
        get_response = await client.get(
            "/api/guilds/123/settings/bot-channels",
            cookies={"session": admin_user_token},
        )
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data == put_data


@pytest.mark.asyncio
async def test_get_discord_channels_proxies_internal_api(admin_user_token):
    """Test GET /api/guilds/{guild_id}/channels/discord proxies to internal API."""
    # Create a mock InternalAPIClient
    mock_client = AsyncMock(spec=InternalAPIClient)
    mock_client.get_guild_channels.return_value = [
        {"id": 111, "name": "general", "category": "Text Channels", "position": 0},
        {"id": 222, "name": "announcements", "category": "Info", "position": 1},
    ]

    # Override the dependency
    def override_get_internal_api_client():
        return mock_client

    app.dependency_overrides[get_internal_api_client] = override_get_internal_api_client

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/guilds/123/channels/discord",
                cookies={"session": admin_user_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["channels"]) == 2
        assert data["channels"][0]["id"] == 111
        assert data["channels"][0]["name"] == "general"
        assert data["channels"][1]["id"] == 222
        assert data["channels"][1]["name"] == "announcements"
    finally:
        # Clean up override
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_bot_channel_settings_allows_nulls(admin_user_token):
    """Test PUT allows setting channels to null."""
    payload = {
        "verification_channel_id": None,
        "bot_spam_channel_id": None,
        "public_announcement_channel_id": None,
        "leadership_announcement_channel_id": None,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            "/api/guilds/123/settings/bot-channels",
            json=payload,
            cookies={"session": admin_user_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert all(v is None for v in data.values())

