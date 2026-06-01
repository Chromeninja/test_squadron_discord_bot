"""Tests for internal ticket forms API routes.

Uses FastAPI dependency_overrides to inject a mock TicketFormRepository.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.internal.ticket_forms import get_ticket_form_repository, router

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
    """Override the TicketFormRepository dependency with an AsyncMock."""
    repo = AsyncMock()
    app.dependency_overrides[get_ticket_form_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()


@pytest.fixture
def async_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. No API key → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_form_config_no_api_key(async_client: AsyncClient) -> None:
    async with async_client as client:
        response = await client.get("/internal/guilds/123/ticket-forms/config/456")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Get form config with valid API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_form_config_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_config: dict[str, Any] = {
        "category_id": 456,
        "steps": [
            {
                "id": 1,
                "category_id": 456,
                "step_number": 1,
                "title": "Basic Info",
                "created_at": 1000,
                "questions": [],
            }
        ],
    }
    mock_repo.get_form_config.return_value = mock_config

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/ticket-forms/config/456",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["config"]["category_id"] == 456
    assert len(data["config"]["steps"]) == 1


# ---------------------------------------------------------------------------
# 3. Get form config not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_form_config_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_form_config.return_value = None

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/ticket-forms/config/999",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
    assert "no form" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Create step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_step(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.create_step.return_value = 1

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/ticket-forms/steps",
            json={
                "category_id": 456,
                "step_number": 1,
                "title": "Step 1",
            },
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["step_id"] == 1


# ---------------------------------------------------------------------------
# 5. Get session not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_not_found(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.get_session.return_value = None

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/ticket-forms/sessions/789",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 6. Create session → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_session: dict[str, Any] = {
        "id": 1,
        "guild_id": 123,
        "user_id": 789,
        "category_id": 456,
        "current_step": 1,
        "collected_data": "{}",
        "interaction_token": None,
        "is_public": 0,
        "created_at": 1000,
        "expires_at": 2000,
    }
    mock_repo.create_session.return_value = mock_session

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/ticket-forms/sessions",
            json={"user_id": 789, "category_id": 456},
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["session"]["user_id"] == 789


# ---------------------------------------------------------------------------
# 7. Validate form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_form(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.validate_form.return_value = []

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/ticket-forms/validate/456",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# 8. Delete step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_step(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.delete_step.return_value = True

    async with async_client as client:
        response = await client.delete(
            "/internal/guilds/123/ticket-forms/steps/1",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# 9. Create question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_question(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.create_question.return_value = 2

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/ticket-forms/questions",
            json={
                "step_id": 1,
                "question_id": "q1",
                "label": "Your name",
                "placeholder": "Enter your full name",
            },
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["question_id"] == 2


# ---------------------------------------------------------------------------
# 10. Save responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_responses(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_repo.save_responses.return_value = True

    async with async_client as client:
        response = await client.post(
            "/internal/guilds/123/ticket-forms/responses/100",
            json={
                "collected_answers": {
                    "q1": {"answer": "John Doe", "label": "Name", "step": 1}
                }
            },
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# 11. Get responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_responses(
    async_client: AsyncClient, mock_repo: AsyncMock
) -> None:
    mock_responses: list[dict[str, Any]] = [
        {
            "id": 1,
            "ticket_id": 100,
            "question_id": "q1",
            "question_label": "Name",
            "answer": "John Doe",
            "step_number": 1,
            "sort_order": 0,
        }
    ]
    mock_repo.get_responses.return_value = mock_responses

    async with async_client as client:
        response = await client.get(
            "/internal/guilds/123/ticket-forms/responses/100",
            headers={"X-Bot-Api-Key": VALID_KEY},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["responses"]) == 1
    assert data["responses"][0]["answer"] == "John Doe"
