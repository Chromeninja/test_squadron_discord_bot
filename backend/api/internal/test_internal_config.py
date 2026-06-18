"""Tests for internal config API routes.

Uses FastAPI dependency_overrides to inject a mock ConfigRepository — the
idiomatic way to test routes without patching module internals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.internal.config import get_config_repository, router

if TYPE_CHECKING:
    from collections.abc import Generator

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
def mock_repo(app: FastAPI) -> Generator[AsyncMock, None, None]:
    """Override the ConfigRepository dependency with an AsyncMock."""
    repo = AsyncMock()
    app.dependency_overrides[get_config_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()


@pytest.fixture
def async_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. No API key → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_no_api_key(async_client: AsyncClient) -> None:
    async with async_client as client:
        response = await client.get("/internal/guilds/123/config")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Valid API key + mocked repo → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_with_api_key(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_config: dict[str, Any] = {
        "prefix": "!",
        "moderation_role_id": 123456,
        "feature_enabled": True,
    }
    mock_repo.get_config.return_value = mock_config

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/config",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert "config" in data
    assert data["config"]["prefix"] == "!"
    assert data["config"]["moderation_role_id"] == 123456


# ---------------------------------------------------------------------------
# 3. GET setting not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_setting_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_setting.return_value = None

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/config/settings/nonexistent",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Setting not found"


# ---------------------------------------------------------------------------
# 4. GET setting found → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_setting_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_setting.return_value = "!"

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/config/settings/prefix",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "prefix"
    assert data["value"] == "!"


# ---------------------------------------------------------------------------
# 5. PATCH setting → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_setting(async_client: AsyncClient, mock_repo: AsyncMock) -> None:
    async with async_client as client:
        response = await client.patch(
            "/internal/guilds/123/config/settings/prefix",
            headers={"X-Bot-Api-Key": VALID_KEY},
            json={"value": "?"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "prefix"
    assert data["value"] == "?"
    mock_repo.set_setting.assert_called_once()


# ---------------------------------------------------------------------------
# 6. POST refresh → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_refresh(async_client: AsyncClient, mock_repo: AsyncMock) -> None:
    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/config/refresh",
            headers={"X-Bot-Api-Key": VALID_KEY},
            json={"source": "webhook"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["refreshed"] is True
    assert data["guild_id"] == 123
    assert data["source"] == "webhook"
