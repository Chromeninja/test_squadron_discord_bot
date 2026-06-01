"""Tests for internal voice API routes.

Uses FastAPI dependency_overrides to inject a mock VoiceRepository — the
idiomatic way to test routes without patching module internals.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.internal.voice import get_voice_repository, router

VALID_KEY = "test-secret-key"


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_API_KEY", VALID_KEY)


@pytest.fixture
def app() -> FastAPI:
    """Fresh app per test so dependency overrides don't leak across tests."""
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def mock_repo(app: FastAPI):
    """Override the VoiceRepository dependency with an AsyncMock."""
    repo = AsyncMock()
    app.dependency_overrides[get_voice_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()


@pytest.fixture
def async_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. No API key → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jtc_channels_no_api_key(async_client: AsyncClient) -> None:
    async with async_client as client:
        response = await client.get("/internal/guilds/123/voice/jtc")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Valid API key + mocked repo → 200 with channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jtc_channels_with_api_key(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_channels: list[dict[str, Any]] = [
        {
            "id": 1,
            "guild_id": 123,
            "jtc_channel_id": 456,
            "owner_id": 789,
            "voice_channel_id": 111,
            "is_active": 1,
        }
    ]
    mock_repo.get_jtc_channels.return_value = mock_channels

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/voice/jtc",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert "channels" in data
    assert len(data["channels"]) == 1
    assert data["channels"][0]["voice_channel_id"] == 111


# ---------------------------------------------------------------------------
# 3. GET single channel not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_voice_channel_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_voice_channel.return_value = None

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/voice/channels/999",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Voice channel not found"


# ---------------------------------------------------------------------------
# 4. GET single channel found → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_voice_channel_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_voice_channel.return_value = {
        "id": 42,
        "guild_id": 123,
        "jtc_channel_id": 456,
        "owner_id": 789,
        "voice_channel_id": 111,
        "is_active": 1,
    }

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/voice/channels/111",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    assert response.json()["channel"]["id"] == 42


# ---------------------------------------------------------------------------
# 5. DELETE channel not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_voice_channel_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.delete_voice_channel.return_value = False

    async with async_client as client:
        response = await client.delete(
            "/internal/guilds/123/voice/channels/999",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 6. POST create channel → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_voice_channel(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.create_voice_channel.return_value = {
        "id": 99,
        "guild_id": 123,
        "jtc_channel_id": 456,
        "owner_id": 789,
        "voice_channel_id": 222,
        "is_active": 1,
    }

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/voice/channels",
            headers={"X-Bot-Api-Key": VALID_KEY},
            json={
                "jtc_channel_id": 456,
                "owner_id": 789,
                "voice_channel_id": 222,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "channel" in data
    assert data["channel"]["id"] == 99
