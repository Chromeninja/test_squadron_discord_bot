"""Tests for internal verification API routes.

Uses FastAPI dependency_overrides to inject a mock VerificationRepository — the
idiomatic way to test routes without patching module internals.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.internal.verification import get_verification_repository, router

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
    """Override the VerificationRepository dependency with an AsyncMock."""
    repo = AsyncMock()
    app.dependency_overrides[get_verification_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()


@pytest.fixture
def async_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. No API key → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_verified_no_api_key(async_client: AsyncClient) -> None:
    async with async_client as client:
        response = await client.get("/internal/guilds/123/verification")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Valid API key + mocked repo → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_verified_with_api_key(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_members: list[dict[str, Any]] = [
        {"user_id": 456, "guild_id": 123, "rsi_handle": "testuser", "main_orgs": None}
    ]
    mock_repo.get_all_verified.return_value = mock_members

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/verification",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert "members" in data
    assert len(data["members"]) == 1
    assert data["members"][0]["rsi_handle"] == "testuser"


# ---------------------------------------------------------------------------
# 3. GET single member not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_member_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_verification.return_value = None

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/verification/members/999",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Verification record not found"


# ---------------------------------------------------------------------------
# 4. GET single member found → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_member_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_verification.return_value = {
        "user_id": 456,
        "guild_id": 123,
        "rsi_handle": "myuser",
        "main_orgs": None,
    }

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/verification/members/456",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    assert response.json()["member"]["user_id"] == 456
    assert response.json()["member"]["rsi_handle"] == "myuser"


# ---------------------------------------------------------------------------
# 5. POST recheck → mock set_needs_reverify returns True → 200 {"queued": True}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recheck_verification(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.set_needs_reverify.return_value = True

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/verification/members/456/recheck",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    assert response.json()["queued"] is True
    mock_repo.set_needs_reverify.assert_called_once_with(456, True)
