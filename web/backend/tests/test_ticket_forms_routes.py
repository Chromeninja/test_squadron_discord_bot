"""
Tests for ticket form API endpoints (/api/tickets/categories/{id}/form).

Uses the ``client``, ``mock_admin_session``, and ``mock_discord_manager_session``
fixtures from the backend test conftest.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_category(
    client: AsyncClient, session: str, *, name: str = "BugReports"
) -> int:
    """Create a ticket category and return its ID."""
    resp = await client.post(
        "/api/tickets/categories",
        json={"guild_id": "123", "name": name},
        cookies={"session": session},
    )
    assert resp.status_code == 201
    cats = resp.json()["categories"]
    return cats[-1]["id"]


def _simple_form_payload() -> dict:
    """Return a minimal valid form config payload."""
    return {
        "steps": [
            {
                "step_number": 1,
                "title": "Basic Info",
                "questions": [
                    {"question_id": "q1", "label": "Name"},
                    {"question_id": "q2", "label": "Email", "style": "short"},
                ],
                "branch_rules": [],
                "default_next_step": None,
            },
        ],
    }


def _branching_form_payload() -> dict:
    """Return a form config with branch rules."""
    return {
        "steps": [
            {
                "step_number": 1,
                "title": "Issue Type",
                "questions": [
                    {"question_id": "issue_type", "label": "Type of Issue"},
                ],
                "branch_rules": [
                    {
                        "question_id": "issue_type",
                        "match_pattern": "(?i)bug",
                        "next_step_number": 2,
                    },
                ],
                "default_next_step": None,
            },
            {
                "step_number": 2,
                "title": "Bug Details",
                "questions": [
                    {
                        "question_id": "repro",
                        "label": "Steps to Reproduce",
                        "style": "paragraph",
                    },
                ],
                "branch_rules": [],
                "default_next_step": None,
            },
        ],
    }


def _ten_question_branching_payload() -> dict:
    """Return a valid branching config with exactly 10 total questions."""
    return {
        "steps": [
            {
                "step_number": 1,
                "title": "Initial",
                "questions": [
                    {"question_id": "q1", "label": "Q1"},
                    {"question_id": "q2", "label": "Q2"},
                    {"question_id": "q3", "label": "Q3"},
                    {"question_id": "q4", "label": "Q4"},
                    {"question_id": "q5", "label": "Q5"},
                ],
                "branch_rules": [
                    {
                        "question_id": "q1",
                        "match_pattern": "(?i)advanced",
                        "next_step_number": 2,
                    }
                ],
                "default_next_step": 2,
            },
            {
                "step_number": 2,
                "title": "Follow-up",
                "questions": [
                    {"question_id": "q6", "label": "Q6"},
                    {"question_id": "q7", "label": "Q7"},
                    {"question_id": "q8", "label": "Q8"},
                    {"question_id": "q9", "label": "Q9"},
                    {"question_id": "q10", "label": "Q10"},
                ],
                "branch_rules": [],
                "default_next_step": None,
            },
        ],
    }


def _eleven_question_payload() -> dict:
    """Return an invalid config with 11 total questions."""
    payload = _ten_question_branching_payload()
    payload["steps"].append(
        {
            "step_number": 3,
            "title": "Extra",
            "questions": [{"question_id": "q11", "label": "Q11"}],
            "branch_rules": [],
            "default_next_step": None,
        }
    )
    return payload


# ---------------------------------------------------------------------------
# GET /categories/{id}/form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_form_empty(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Getting form config when none exists returns empty steps."""
    cat_id = await _create_category(client, mock_admin_session)

    resp = await client.get(
        f"/api/tickets/categories/{cat_id}/form",
        cookies={"session": mock_admin_session},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["category_id"] == cat_id
    assert data["config"]["steps"] == []


@pytest.mark.asyncio
async def test_get_form_not_found(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Getting form for a non-existent category returns 404."""
    resp = await client.get(
        "/api/tickets/categories/99999/form",
        cookies={"session": mock_admin_session},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_form_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated requests return 401."""
    resp = await client.get("/api/tickets/categories/1/form")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /categories/{id}/form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_form_creates_config(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Replacing form config stores the steps and questions."""
    cat_id = await _create_category(client, mock_discord_manager_session)

    resp = await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_simple_form_payload(),
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 200
    data = resp.json()
    config = data["config"]
    assert config["category_id"] == cat_id
    assert len(config["steps"]) == 1
    assert len(config["steps"][0]["questions"]) == 2


@pytest.mark.asyncio
async def test_put_form_replaces_existing(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Re-submitting replaces old config entirely."""
    cat_id = await _create_category(client, mock_discord_manager_session, name="Replace")

    # First config
    await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_simple_form_payload(),
        cookies={"session": mock_discord_manager_session},
    )

    # Replace with branching config
    resp = await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_branching_form_payload(),
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert len(config["steps"]) == 2
    assert config["steps"][0]["title"] == "Issue Type"


@pytest.mark.asyncio
async def test_put_form_not_found(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Replacing form for non-existent category returns 404."""
    resp = await client.put(
        "/api/tickets/categories/99999/form",
        json=_simple_form_payload(),
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_form_requires_discord_manager(
    client: AsyncClient,
    mock_admin_session: str,
    mock_moderator_session: str,
) -> None:
    """Moderators cannot replace form config (requires discord_manager)."""
    cat_id = await _create_category(client, mock_admin_session)

    resp = await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_simple_form_payload(),
        cookies={"session": mock_moderator_session},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_form_allows_exactly_10_questions(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """A branching payload with 10 total questions should save successfully."""
    cat_id = await _create_category(client, mock_discord_manager_session, name="TenQs")

    resp = await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_ten_question_branching_payload(),
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 200
    steps = resp.json()["config"]["steps"]
    total_questions = sum(len(step["questions"]) for step in steps)
    assert total_questions == 10


@pytest.mark.asyncio
async def test_put_form_rejects_more_than_10_questions(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """A category form with more than 10 total questions should be rejected."""
    cat_id = await _create_category(
        client, mock_discord_manager_session, name="TooManyQuestions"
    )

    resp = await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_eleven_question_payload(),
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["message"] == "Invalid form config"
    assert any("total questions" in err for err in detail["errors"])


# ---------------------------------------------------------------------------
# DELETE /categories/{id}/form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_form(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Deleting form config clears all steps."""
    cat_id = await _create_category(client, mock_discord_manager_session, name="Del")

    # Create form
    await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_simple_form_payload(),
        cookies={"session": mock_discord_manager_session},
    )

    # Delete form
    resp = await client.delete(
        f"/api/tickets/categories/{cat_id}/form",
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["steps"] == []

    # Verify it's gone
    get_resp = await client.get(
        f"/api/tickets/categories/{cat_id}/form",
        cookies={"session": mock_discord_manager_session},
    )
    assert get_resp.json()["config"]["steps"] == []


@pytest.mark.asyncio
async def test_delete_form_not_found(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Deleting form for non-existent category returns 404."""
    resp = await client.delete(
        "/api/tickets/categories/99999/form",
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_form_requires_discord_manager(
    client: AsyncClient,
    mock_admin_session: str,
    mock_moderator_session: str,
) -> None:
    """Moderators cannot delete form config."""
    cat_id = await _create_category(client, mock_admin_session, name="NoMod")

    resp = await client.delete(
        f"/api/tickets/categories/{cat_id}/form",
        cookies={"session": mock_moderator_session},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /categories/{id}/form/validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_no_form(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Validation of a category with no form returns errors."""
    cat_id = await _create_category(client, mock_admin_session, name="NoForm")

    resp = await client.get(
        f"/api/tickets/categories/{cat_id}/form/validate",
        cookies={"session": mock_admin_session},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


@pytest.mark.asyncio
async def test_validate_valid_form(
    client: AsyncClient, mock_discord_manager_session: str
) -> None:
    """Validation of a properly configured form returns valid=True."""
    cat_id = await _create_category(
        client, mock_discord_manager_session, name="Valid"
    )

    await client.put(
        f"/api/tickets/categories/{cat_id}/form",
        json=_simple_form_payload(),
        cookies={"session": mock_discord_manager_session},
    )

    resp = await client.get(
        f"/api/tickets/categories/{cat_id}/form/validate",
        cookies={"session": mock_discord_manager_session},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_validate_not_found(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Validating a non-existent category returns 404."""
    resp = await client.get(
        "/api/tickets/categories/99999/form/validate",
        cookies={"session": mock_admin_session},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /{ticket_id}/responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_responses_no_ticket(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Getting responses for a non-existent ticket returns 404."""
    resp = await client.get(
        "/api/tickets/99999/responses",
        cookies={"session": mock_admin_session},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_responses_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    resp = await client.get("/api/tickets/1/responses")
    assert resp.status_code == 401
