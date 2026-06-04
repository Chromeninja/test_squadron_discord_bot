"""Tests for internal tickets API routes.

Uses FastAPI dependency_overrides to inject a mock TicketRepository — the
idiomatic way to test routes without patching module internals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.internal.tickets import get_ticket_repository, router

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
    """Override the TicketRepository dependency with an AsyncMock."""
    repo = AsyncMock()
    app.dependency_overrides[get_ticket_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()


@pytest.fixture
def async_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. No API key → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tickets_no_api_key(async_client: AsyncClient) -> None:
    async with async_client as client:
        response = await client.get("/internal/guilds/123/tickets")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Valid API key + mocked repo → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tickets_with_api_key(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_tickets: list[dict[str, Any]] = [
        {"id": 1, "guild_id": 123, "thread_id": 456, "user_id": 789, "status": "open"}
    ]
    mock_repo.get_tickets.return_value = mock_tickets

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/tickets",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert "tickets" in data
    assert len(data["tickets"]) == 1
    assert data["tickets"][0]["thread_id"] == 456


# ---------------------------------------------------------------------------
# 3. GET single ticket not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ticket_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_ticket.return_value = None

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/tickets/999",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


# ---------------------------------------------------------------------------
# 4. GET single ticket found → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ticket_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_ticket.return_value = {
        "id": 42,
        "guild_id": 123,
        "thread_id": 456,
        "status": "open",
    }

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/tickets/42",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    assert response.json()["ticket"]["id"] == 42


# ---------------------------------------------------------------------------
# 5. POST create with missing field → mock repo.create_ticket.side_effect = ValueError → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ticket_missing_field(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.create_ticket.side_effect = ValueError("missing thread_id")

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/tickets",
            json={"channel_id": 456, "user_id": 789},
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 422
    assert "missing thread_id" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 6. DELETE ticket not found → mock delete_ticket returns False → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_ticket_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.delete_ticket.return_value = False

    async with async_client as client:
        response = await client.delete(
            "/internal/guilds/123/tickets/999",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
