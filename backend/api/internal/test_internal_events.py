"""Tests for internal events API routes."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.internal.events import router

# Build a minimal test app
app = FastAPI()
app.include_router(router)

VALID_KEY = "test-secret-key"


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_API_KEY", VALID_KEY)


@pytest.fixture
def async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. No API key → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_no_api_key(async_client: AsyncClient) -> None:
    async with async_client as client:
        response = await client.get("/internal/guilds/123/managed-events")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Valid API key + mocked repo → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_with_api_key(async_client: AsyncClient) -> None:
    mock_events: list[dict[str, Any]] = [
        {"id": 1, "guild_id": 123, "name": "Test Event", "status": "scheduled"}
    ]
    with patch(
        "backend.api.internal.events._repo.get_managed_events",
        new=AsyncMock(return_value=mock_events),
    ):
        async with async_client as client:
            response = await client.get(
                "/internal/guilds/123/managed-events",
                headers={"X-Bot-Api-Key": VALID_KEY},
            )
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert len(data["events"]) == 1
    assert data["events"][0]["name"] == "Test Event"


# ---------------------------------------------------------------------------
# 3. GET single event not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_event_not_found(async_client: AsyncClient) -> None:
    with patch(
        "backend.api.internal.events._repo.get_managed_event",
        new=AsyncMock(return_value=None),
    ):
        async with async_client as client:
            response = await client.get(
                "/internal/guilds/123/managed-events/999",
                headers={"X-Bot-Api-Key": VALID_KEY},
            )
    assert response.status_code == 404
    assert response.json()["detail"] == "Managed event not found"


# ---------------------------------------------------------------------------
# 4. GET single event found → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_event_found(async_client: AsyncClient) -> None:
    mock_event: dict[str, Any] = {"id": 42, "guild_id": 123, "name": "My Event"}
    with patch(
        "backend.api.internal.events._repo.get_managed_event",
        new=AsyncMock(return_value=mock_event),
    ):
        async with async_client as client:
            response = await client.get(
                "/internal/guilds/123/managed-events/42",
                headers={"X-Bot-Api-Key": VALID_KEY},
            )
    assert response.status_code == 200
    assert response.json()["event"]["id"] == 42


# ---------------------------------------------------------------------------
# 5. DELETE event not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_event_not_found(async_client: AsyncClient) -> None:
    with patch(
        "backend.api.internal.events._repo.delete",
        new=AsyncMock(return_value=False),
    ):
        async with async_client as client:
            response = await client.delete(
                "/internal/guilds/123/managed-events/999",
                headers={"X-Bot-Api-Key": VALID_KEY},
            )
    assert response.status_code == 404
