"""
Tests for TicketFormService — step/question CRUD, form config, branch
resolution, route sessions, form responses, and validation.

Uses the ``temp_db`` fixture from conftest so each test gets an isolated database.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
import pytest_asyncio

from helpers.constants import (
    MAX_FORM_STEPS,
    MAX_QUESTIONS_PER_STEP,
    MAX_TOTAL_FORM_QUESTIONS,
)
from services.db.repository import BaseRepository
from services.ticket_form_service import RouteExecutionContext, TicketFormService
from services.ticket_service import TicketService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GUILD_ID = 100
USER_ID = 200
CHANNEL_ID = 300


@pytest_asyncio.fixture
async def ticket_svc(temp_db: str) -> TicketService:
    """Provide an initialised TicketService backed by the temp database."""
    svc = TicketService()
    svc._initialized = True
    return svc


@pytest_asyncio.fixture
async def form_svc(temp_db: str) -> TicketFormService:
    """Provide an initialised TicketFormService backed by the temp database."""
    svc = TicketFormService()
    svc._initialized = True
    return svc


@pytest_asyncio.fixture
async def category_id(ticket_svc: TicketService) -> int:
    """Create a test category and return its ID."""
    cat_id = await ticket_svc.create_category(
        guild_id=GUILD_ID,
        name="Bug Reports",
        description="Report bugs here",
    )
    assert cat_id is not None
    return cat_id


@pytest_asyncio.fixture
async def step_id(form_svc: TicketFormService, category_id: int) -> int:
    """Create a test step and return its ID."""
    sid = await form_svc.create_step(category_id, step_number=1, title="Step 1")
    assert sid is not None
    return sid


# ---------------------------------------------------------------------------
# Step CRUD
# ---------------------------------------------------------------------------


class TestStepCRUD:
    """Tests for form step create / read / update / delete."""

    @pytest.mark.asyncio
    async def test_create_step(self, form_svc, category_id) -> None:
        sid = await form_svc.create_step(category_id, step_number=1, title="Info")
        assert sid is not None
        assert sid > 0

    @pytest.mark.asyncio
    async def test_get_steps_empty(self, form_svc, category_id) -> None:
        steps = await form_svc.get_steps(category_id)
        assert steps == []

    @pytest.mark.asyncio
    async def test_get_steps_ordered(self, form_svc, category_id) -> None:
        await form_svc.create_step(category_id, step_number=2, title="Two")
        await form_svc.create_step(category_id, step_number=1, title="One")
        steps = await form_svc.get_steps(category_id)
        assert len(steps) == 2
        assert steps[0]["step_number"] == 1
        assert steps[1]["step_number"] == 2

    @pytest.mark.asyncio
    async def test_get_step_by_number(self, form_svc, category_id) -> None:
        await form_svc.create_step(category_id, step_number=1, title="First")
        step = await form_svc.get_step(category_id, step_number=1)
        assert step is not None
        assert step["title"] == "First"

    @pytest.mark.asyncio
    async def test_get_step_not_found(self, form_svc, category_id) -> None:
        step = await form_svc.get_step(category_id, step_number=99)
        assert step is None

    @pytest.mark.asyncio
    async def test_update_step(self, form_svc, category_id) -> None:
        sid = await form_svc.create_step(category_id, step_number=1, title="Old")
        assert sid is not None
        updated = await form_svc.update_step(sid, title="New")
        assert updated is True
        step = await form_svc.get_step(category_id, 1)
        assert step is not None
        assert step["title"] == "New"

    @pytest.mark.asyncio
    async def test_update_step_with_unknown_field_is_ignored(self, form_svc, category_id) -> None:
        sid = await form_svc.create_step(category_id, step_number=1)
        assert sid is not None
        updated = await form_svc.update_step(sid, unknown_field="value")
        assert updated is False
        step = await form_svc.get_step(category_id, 1)
        assert step is not None
        assert step["title"] == ""

    @pytest.mark.asyncio
    async def test_delete_step(self, form_svc, category_id) -> None:
        sid = await form_svc.create_step(category_id, step_number=1)
        assert sid is not None
        deleted = await form_svc.delete_step(sid)
        assert deleted is True
        steps = await form_svc.get_steps(category_id)
        assert len(steps) == 0

    @pytest.mark.asyncio
    async def test_delete_step_not_found(self, form_svc) -> None:
        deleted = await form_svc.delete_step(99999)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_max_steps_enforced(self, form_svc, category_id) -> None:
        """Cannot create more than MAX_FORM_STEPS steps."""
        for i in range(1, MAX_FORM_STEPS + 1):
            sid = await form_svc.create_step(category_id, step_number=i)
            assert sid is not None

        # One over the limit
        extra = await form_svc.create_step(
            category_id, step_number=MAX_FORM_STEPS + 1
        )
        assert extra is None

    @pytest.mark.asyncio
    async def test_step_defaults_without_branching(self, form_svc, category_id) -> None:
        sid = await form_svc.create_step(category_id, step_number=1)
        assert sid is not None
        step = await form_svc.get_step(category_id, 1)
        assert step is not None
        assert step["step_number"] == 1


# ---------------------------------------------------------------------------
# Question CRUD
# ---------------------------------------------------------------------------


class TestQuestionCRUD:
    """Tests for form question create / read / update / delete."""

    @pytest.mark.asyncio
    async def test_create_question(self, form_svc, step_id) -> None:
        qid = await form_svc.create_question(
            step_id, "issue_type", "Type of Issue",
            style="short", required=True,
        )
        assert qid is not None
        assert qid > 0

    @pytest.mark.asyncio
    async def test_get_questions_empty(self, form_svc, step_id) -> None:
        questions = await form_svc.get_questions(step_id)
        assert questions == []

    @pytest.mark.asyncio
    async def test_get_questions_ordered(self, form_svc, step_id) -> None:
        await form_svc.create_question(
            step_id, "q2", "Second", sort_order=2
        )
        await form_svc.create_question(
            step_id, "q1", "First", sort_order=1
        )
        questions = await form_svc.get_questions(step_id)
        assert len(questions) == 2
        assert questions[0]["question_id"] == "q1"
        assert questions[1]["question_id"] == "q2"

    @pytest.mark.asyncio
    async def test_question_fields(self, form_svc, step_id) -> None:
        await form_svc.create_question(
            step_id, "desc", "Description",
            placeholder="Enter here",
            style="paragraph",
            required=False,
            min_length=10,
            max_length=500,
            sort_order=0,
        )
        questions = await form_svc.get_questions(step_id)
        q = questions[0]
        assert q["question_id"] == "desc"
        assert q["label"] == "Description"
        assert q["placeholder"] == "Enter here"
        assert q["style"] == "paragraph"
        assert q["required"] is False
        assert q["min_length"] == 10
        assert q["max_length"] == 500

    @pytest.mark.asyncio
    async def test_update_question(self, form_svc, step_id) -> None:
        pk = await form_svc.create_question(step_id, "q1", "Old Label")
        assert pk is not None
        updated = await form_svc.update_question(pk, label="New Label")
        assert updated is True
        questions = await form_svc.get_questions(step_id)
        assert questions[0]["label"] == "New Label"

    @pytest.mark.asyncio
    async def test_delete_question(self, form_svc, step_id) -> None:
        pk = await form_svc.create_question(step_id, "q1", "Test")
        assert pk is not None
        deleted = await form_svc.delete_question(pk)
        assert deleted is True
        questions = await form_svc.get_questions(step_id)
        assert len(questions) == 0

    @pytest.mark.asyncio
    async def test_max_questions_enforced(self, form_svc, step_id) -> None:
        """Cannot create more than MAX_QUESTIONS_PER_STEP questions."""
        for i in range(MAX_QUESTIONS_PER_STEP):
            qid = await form_svc.create_question(
                step_id, f"q{i}", f"Question {i}"
            )
            assert qid is not None

        extra = await form_svc.create_question(step_id, "extra", "Extra")
        assert extra is None

    @pytest.mark.asyncio
    async def test_delete_question_not_found(self, form_svc) -> None:
        deleted = await form_svc.delete_question(99999)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_create_select_question_rejected(self, form_svc, step_id) -> None:
        """Dropdown/select questions are no longer supported."""
        pk = await form_svc.create_question(
            step_id,
            "issue_type",
            "Issue Type",
            input_type="select",
            options=[{"value": "billing", "label": "Billing"}],
        )
        assert pk is None


# ---------------------------------------------------------------------------
# Form Config
# ---------------------------------------------------------------------------


class TestFormConfig:
    """Tests for get_form_config, has_form, validate_form, replace/delete."""

    @pytest.mark.asyncio
    async def test_has_form_false_when_empty(self, form_svc, category_id) -> None:
        assert await form_svc.has_form(category_id) is False

    @pytest.mark.asyncio
    async def test_has_form_true_when_steps_exist(
        self, form_svc, category_id, step_id
    ) -> None:
        assert await form_svc.has_form(category_id) is True

    @pytest.mark.asyncio
    async def test_get_form_config_none_when_empty(
        self, form_svc, category_id
    ) -> None:
        config = await form_svc.get_form_config(category_id)
        assert config is None

    @pytest.mark.asyncio
    async def test_get_form_config_with_steps_and_questions(
        self, form_svc, category_id, step_id
    ) -> None:
        await form_svc.create_question(step_id, "q1", "Question 1")
        config = await form_svc.get_form_config(category_id)
        assert config is not None
        assert config["category_id"] == category_id
        assert len(config["steps"]) == 1
        assert len(config["steps"][0]["questions"]) == 1

    @pytest.mark.asyncio
    async def test_form_config_cached(self, form_svc, category_id, step_id) -> None:
        """Second call returns cached result."""
        await form_svc.create_question(step_id, "q1", "Question 1")
        c1 = await form_svc.get_form_config(category_id)
        c2 = await form_svc.get_form_config(category_id)
        assert c1 is c2  # Same object (cached)

    @pytest.mark.asyncio
    async def test_form_config_cache_invalidated_on_create(
        self, form_svc, category_id, step_id
    ) -> None:
        """Creating a question invalidates the config cache."""
        await form_svc.create_question(step_id, "q1", "Question 1")
        c1 = await form_svc.get_form_config(category_id)
        await form_svc.create_question(step_id, "q2", "Question 2")
        c2 = await form_svc.get_form_config(category_id)
        assert c1 is not c2

    @pytest.mark.asyncio
    async def test_replace_form_config(self, form_svc, category_id) -> None:
        steps_data = [
            {
                "step_number": 1,
                "title": "Info",
                "questions": [
                    {"question_id": "q1", "label": "Name"},
                    {"question_id": "q2", "label": "Email", "style": "short"},
                ],
            },
            {
                "step_number": 2,
                "title": "Details",
                "questions": [
                    {"question_id": "q3", "label": "Description", "style": "paragraph"},
                ],
            },
        ]
        result = await form_svc.replace_form_config(category_id, steps_data)
        assert result is True

        config = await form_svc.get_form_config(category_id)
        assert config is not None
        assert len(config["steps"]) == 2
        assert len(config["steps"][0]["questions"]) == 2
        assert len(config["steps"][1]["questions"]) == 1

    @pytest.mark.asyncio
    async def test_replace_form_config_replaces_existing(
        self, form_svc, category_id
    ) -> None:
        """Replacing config deletes old steps and creates new ones."""
        await form_svc.replace_form_config(category_id, [
            {"step_number": 1, "title": "Old", "questions": [
                {"question_id": "old_q", "label": "Old Q"},
            ]},
        ])
        await form_svc.replace_form_config(category_id, [
            {"step_number": 1, "title": "New", "questions": [
                {"question_id": "new_q", "label": "New Q"},
            ]},
        ])
        config = await form_svc.get_form_config(category_id)
        assert config is not None
        assert config["steps"][0]["title"] == "New"
        assert config["steps"][0]["questions"][0]["question_id"] == "new_q"

    @pytest.mark.asyncio
    async def test_replace_form_config_rejects_more_than_10_questions(
        self, form_svc, category_id
    ) -> None:
        """Category form payload must not exceed 10 total questions."""
        steps_data = [
            {
                "step_number": 1,
                "title": "Step 1",
                "questions": [
                    {"question_id": f"q{i}", "label": f"Question {i}"}
                    for i in range(1, 7)
                ],
            },
            {
                "step_number": 2,
                "title": "Step 2",
                "questions": [
                    {"question_id": f"q{i}", "label": f"Question {i}"}
                    for i in range(7, 12)
                ],
            },
        ]

        result = await form_svc.replace_form_config(category_id, steps_data)
        assert result is False
        assert await form_svc.get_form_config(category_id) is None

    @pytest.mark.asyncio
    async def test_validate_form_payload_accepts_up_to_10_questions(
        self, form_svc
    ) -> None:
        """Payload validation allows exactly MAX_TOTAL_FORM_QUESTIONS."""
        steps_data = [
            {
                "step_number": 1,
                "title": "Step 1",
                "questions": [
                    {"question_id": f"a{i}", "label": f"A{i}"}
                    for i in range(1, 6)
                ],
            },
            {
                "step_number": 2,
                "title": "Step 2",
                "questions": [
                    {"question_id": f"b{i}", "label": f"B{i}"}
                    for i in range(1, 6)
                ],
            },
        ]

        errors = form_svc.validate_form_payload(steps_data)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_form_payload_rejects_more_than_10_questions(
        self, form_svc
    ) -> None:
        """Payload validation rejects forms above MAX_TOTAL_FORM_QUESTIONS."""
        steps_data = [
            {
                "step_number": 1,
                "title": "Step 1",
                "questions": [
                    {"question_id": f"q{i}", "label": f"Q{i}"}
                    for i in range(1, MAX_TOTAL_FORM_QUESTIONS + 2)
                ],
            },
        ]

        errors = form_svc.validate_form_payload(steps_data)
        assert any("total questions" in error for error in errors)

    @pytest.mark.asyncio
    async def test_delete_form_config(self, form_svc, category_id, step_id) -> None:
        await form_svc.create_question(step_id, "q1", "Q1")
        result = await form_svc.delete_form_config(category_id)
        assert result is True
        assert await form_svc.has_form(category_id) is False

    @pytest.mark.asyncio
    async def test_validate_form_no_steps(self, form_svc, category_id) -> None:
        errors = await form_svc.validate_form(category_id)
        assert len(errors) == 1
        assert "No form steps" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_form_empty_step(self, form_svc, category_id) -> None:
        await form_svc.create_step(category_id, step_number=1, title="Empty")
        errors = await form_svc.validate_form(category_id)
        assert any("no questions" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_form_ignores_extra_unknown_fields(self, form_svc, category_id) -> None:
        sid = await form_svc.create_step(category_id, step_number=1)
        assert sid is not None
        await form_svc.create_question(sid, "q1", "Q1")

        errors = form_svc.validate_form_payload(
            [
                {
                    "step_number": 1,
                    "title": "Info",
                    "questions": [{"question_id": "q1", "label": "Q1"}],
                    "unexpected": "ignored",
                },
            ]
        )
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_form_valid(self, form_svc, category_id) -> None:
        """A properly configured form should have zero errors."""
        await form_svc.replace_form_config(category_id, [
            {
                "step_number": 1,
                "title": "Info",
                "questions": [{"question_id": "q1", "label": "Name"}],
            },
            {
                "step_number": 2,
                "title": "Bug Details",
                "questions": [{"question_id": "q2", "label": "Details"}],
            },
        ])
        errors = await form_svc.validate_form(category_id)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_payload_rejects_select_input_type(self, form_svc) -> None:
        """Dropdown/select question types are rejected."""
        errors = form_svc.validate_form_payload(
            [
                {
                    "step_number": 1,
                    "title": "Type",
                    "questions": [
                        {
                            "question_id": "issue_type",
                            "label": "Issue Type",
                            "input_type": "select",
                            "options": [],
                        },
                    ],
                },
            ]
        )
        assert any("invalid input_type" in error for error in errors)

    @pytest.mark.asyncio
    async def test_validate_payload_rejects_mixed_select_and_text(self, form_svc) -> None:
        """Any step containing select question type is invalid."""
        errors = form_svc.validate_form_payload(
            [
                {
                    "step_number": 1,
                    "title": "Mixed",
                    "questions": [
                        {
                            "question_id": "issue_type",
                            "label": "Issue Type",
                            "input_type": "select",
                            "options": [{"value": "a", "label": "A"}],
                        },
                        {
                            "question_id": "details",
                            "label": "Details",
                            "input_type": "text",
                        },
                    ],
                },
            ]
        )
        assert any("invalid input_type" in error for error in errors)


# ---------------------------------------------------------------------------
# Branch Resolution
# ---------------------------------------------------------------------------


class TestBranchResolution:
    """Tests for sequential resolve_next_step behavior."""

    @pytest.mark.asyncio
    async def test_resolve_terminal_last_step(self, form_svc, category_id) -> None:
        """Last step resolves to terminal (None)."""
        sid = await form_svc.create_step(category_id, step_number=1)
        assert sid is not None
        await form_svc.create_question(sid, "q1", "Q1")

        next_step = await form_svc.resolve_next_step(
            category_id, 1, {"q1": {"answer": "anything"}}
        )
        assert next_step is None

    @pytest.mark.asyncio
    async def test_resolve_returns_next_step_when_present(self, form_svc, category_id) -> None:
        """Any non-final step resolves to the next sequential step."""
        await form_svc.create_step(category_id, step_number=1)
        await form_svc.create_step(category_id, step_number=2, title="Bug Details")

        next_step = await form_svc.resolve_next_step(
            category_id, 1,
            {"issue": {"answer": "This is a Bug report"}}
        )
        assert next_step == 2

    @pytest.mark.asyncio
    async def test_resolve_skips_to_none_when_next_missing(self, form_svc, category_id) -> None:
        """If next sequential step is missing, flow terminates."""
        await form_svc.create_step(category_id, step_number=1)
        await form_svc.create_step(category_id, step_number=3, title="Skipped")

        next_step = await form_svc.resolve_next_step(
            category_id, 1,
            {"issue": {"answer": "question about something"}}
        )
        assert next_step is None

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_step(self, form_svc, category_id) -> None:
        """Resolving on a nonexistent step returns None."""
        next_step = await form_svc.resolve_next_step(
            category_id, 99, {"q1": {"answer": "test"}}
        )
        assert next_step is None

    @pytest.mark.asyncio
    async def test_resolve_ignores_answers(self, form_svc, category_id) -> None:
        """Sequential resolution does not depend on collected answers."""
        await form_svc.create_step(category_id, step_number=1)
        await form_svc.create_step(category_id, step_number=2)

        next_step = await form_svc.resolve_next_step(
            category_id, 1, {"unused": {"answer": "anything"}}
        )
        assert next_step == 2


# ---------------------------------------------------------------------------
# Session State Management
# ---------------------------------------------------------------------------


class TestSessionManagement:
    """Tests for route session create / get / update / delete / cleanup."""

    @pytest.mark.asyncio
    async def test_create_session(self, form_svc, category_id) -> None:
        ctx = await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        assert ctx.guild_id == GUILD_ID
        assert ctx.user_id == USER_ID
        assert ctx.category_id == category_id
        assert ctx.current_step == 1
        assert ctx.collected_answers == {}
        assert not ctx.is_expired()

    @pytest.mark.asyncio
    async def test_get_session(self, form_svc, category_id) -> None:
        await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        ctx = await form_svc.get_session(GUILD_ID, USER_ID)
        assert ctx is not None
        assert ctx.category_id == category_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, form_svc) -> None:
        ctx = await form_svc.get_session(GUILD_ID, 99999)
        assert ctx is None

    @pytest.mark.asyncio
    async def test_update_session(self, form_svc, category_id) -> None:
        await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        answers = {"q1": {"answer": "bug", "label": "Type"}}
        result = await form_svc.update_session(
            GUILD_ID, USER_ID, step=2, answers=answers
        )
        assert result is True

        ctx = await form_svc.get_session(GUILD_ID, USER_ID)
        assert ctx is not None
        assert ctx.current_step == 2
        assert "q1" in ctx.collected_answers

    @pytest.mark.asyncio
    async def test_update_session_merges_answers(
        self, form_svc, category_id
    ) -> None:
        """Updating preserves previously collected answers."""
        await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        await form_svc.update_session(
            GUILD_ID, USER_ID, step=2,
            answers={"q1": {"answer": "a1", "label": "Q1"}},
        )
        await form_svc.update_session(
            GUILD_ID, USER_ID, step=3,
            answers={"q2": {"answer": "a2", "label": "Q2"}},
        )
        ctx = await form_svc.get_session(GUILD_ID, USER_ID)
        assert ctx is not None
        assert "q1" in ctx.collected_answers
        assert "q2" in ctx.collected_answers

    @pytest.mark.asyncio
    async def test_delete_session(self, form_svc, category_id) -> None:
        await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        deleted = await form_svc.delete_session(GUILD_ID, USER_ID)
        assert deleted is True
        ctx = await form_svc.get_session(GUILD_ID, USER_ID)
        assert ctx is None

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, form_svc) -> None:
        deleted = await form_svc.delete_session(GUILD_ID, 99999)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_expired_session_returns_none(
        self, form_svc, category_id
    ) -> None:
        """Expired sessions are automatically deleted on get."""
        ctx = await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        # Force expiry
        ctx.expires_at = time.time() - 1
        async with form_svc._session_lock:
            form_svc._session_cache[(GUILD_ID, USER_ID)] = ctx

        result = await form_svc.get_session(GUILD_ID, USER_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_session_replaces_existing(
        self, form_svc, category_id, ticket_svc
    ) -> None:
        """Creating a new session replaces any existing one for the same user."""
        cat2 = await ticket_svc.create_category(GUILD_ID, "Other")
        assert cat2 is not None

        await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        await form_svc.create_session(GUILD_ID, USER_ID, cat2)
        ctx = await form_svc.get_session(GUILD_ID, USER_ID)
        assert ctx is not None
        assert ctx.category_id == cat2

    @pytest.mark.asyncio
    async def test_session_with_interaction_token(
        self, form_svc, category_id
    ) -> None:
        ctx = await form_svc.create_session(
            GUILD_ID, USER_ID, category_id,
            interaction_token="test_token_123",
        )
        assert ctx.interaction_token == "test_token_123"

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(
        self, form_svc, category_id, ticket_svc
    ) -> None:
        """cleanup_expired_sessions removes only expired sessions."""
        # Create an active session
        cat2 = await ticket_svc.create_category(GUILD_ID, "Active")
        assert cat2 is not None
        await form_svc.create_session(GUILD_ID, USER_ID, category_id)

        # Create an expired session for a different user
        expired_ctx = await form_svc.create_session(GUILD_ID, 999, cat2)
        expired_ctx.expires_at = time.time() - 100
        async with form_svc._session_lock:
            form_svc._session_cache[(GUILD_ID, 999)] = expired_ctx
        # Also update DB
        await BaseRepository.execute(
            "UPDATE ticket_route_sessions SET expires_at = ? "
            "WHERE guild_id = ? AND user_id = ?",
            (int(time.time()) - 100, GUILD_ID, 999),
        )

        cleaned = await form_svc.cleanup_expired_sessions()
        assert cleaned >= 1

        # Active session should still exist
        active = await form_svc.get_session(GUILD_ID, USER_ID)
        assert active is not None

    @pytest.mark.asyncio
    async def test_session_db_fallback(self, form_svc, category_id) -> None:
        """get_session falls back to DB when cache is empty."""
        await form_svc.create_session(GUILD_ID, USER_ID, category_id)
        # Clear cache
        async with form_svc._session_lock:
            form_svc._session_cache.clear()

        ctx = await form_svc.get_session(GUILD_ID, USER_ID)
        assert ctx is not None
        assert ctx.category_id == category_id


# ---------------------------------------------------------------------------
# Form Response Storage
# ---------------------------------------------------------------------------


class TestFormResponses:
    """Tests for save_responses and get_responses."""

    @pytest.mark.asyncio
    async def test_save_and_get_responses(
        self, form_svc, ticket_svc, category_id
    ) -> None:
        """Responses are saved and retrieved correctly."""
        ticket_id = await ticket_svc.create_ticket(
            guild_id=GUILD_ID,
            channel_id=CHANNEL_ID,
            thread_id=1001,
            user_id=USER_ID,
            category_id=category_id,
        )
        assert ticket_id is not None

        answers = {
            "q1": {"answer": "Bug report", "label": "Type", "step": 1, "sort_order": 0},
            "q2": {"answer": "It crashes", "label": "Description", "step": 1, "sort_order": 1},
        }
        result = await form_svc.save_responses(ticket_id, answers)
        assert result is True

        responses = await form_svc.get_responses(ticket_id)
        assert len(responses) == 2
        assert responses[0]["question_id"] == "q1"
        assert responses[0]["answer"] == "Bug report"
        assert responses[1]["question_id"] == "q2"
        assert responses[1]["answer"] == "It crashes"

    @pytest.mark.asyncio
    async def test_save_empty_responses(self, form_svc) -> None:
        """Saving empty responses succeeds silently."""
        result = await form_svc.save_responses(1, {})
        assert result is True

    @pytest.mark.asyncio
    async def test_get_responses_empty(self, form_svc) -> None:
        """Getting responses for a ticket with none returns empty list."""
        responses = await form_svc.get_responses(99999)
        assert responses == []

    @pytest.mark.asyncio
    async def test_responses_ordered_by_step_and_sort(
        self, form_svc, ticket_svc, category_id
    ) -> None:
        ticket_id = await ticket_svc.create_ticket(
            guild_id=GUILD_ID,
            channel_id=CHANNEL_ID,
            thread_id=2001,
            user_id=USER_ID,
        )
        assert ticket_id is not None

        answers = {
            "q3": {"answer": "Step 2 Q1", "label": "Q3", "step": 2, "sort_order": 0},
            "q1": {"answer": "Step 1 Q1", "label": "Q1", "step": 1, "sort_order": 0},
            "q2": {"answer": "Step 1 Q2", "label": "Q2", "step": 1, "sort_order": 1},
        }
        await form_svc.save_responses(ticket_id, answers)
        responses = await form_svc.get_responses(ticket_id)

        assert responses[0]["step_number"] == 1
        assert responses[0]["sort_order"] == 0
        assert responses[1]["step_number"] == 1
        assert responses[1]["sort_order"] == 1
        assert responses[2]["step_number"] == 2


# ---------------------------------------------------------------------------
# Schema Compatibility
# ---------------------------------------------------------------------------


class TestSchemaCompatibility:
    """Tests for legacy schema compatibility in question storage."""

    @pytest.mark.asyncio
    async def test_adds_missing_question_columns(
        self, form_svc: TicketFormService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing columns are added for legacy ticket_form_questions tables."""

        async def fake_fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:  # noqa: ARG001
            if query.startswith("PRAGMA table_info(ticket_form_questions)"):
                return [
                    {"name": "id"},
                    {"name": "step_id"},
                    {"name": "question_id"},
                    {"name": "label"},
                ]
            return []

        executed_queries: list[str] = []

        async def fake_execute(query: str, params: tuple[Any, ...] = ()) -> int:  # noqa: ARG001
            executed_queries.append(query)
            return 1

        monkeypatch.setattr(BaseRepository, "fetch_all", fake_fetch_all)
        monkeypatch.setattr(BaseRepository, "execute", fake_execute)

        await form_svc._ensure_question_schema_compatibility()

        assert any("ADD COLUMN input_type" in query for query in executed_queries)
        assert any("ADD COLUMN options_json" in query for query in executed_queries)

    @pytest.mark.asyncio
    async def test_schema_check_runs_only_once(
        self, form_svc: TicketFormService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Schema compatibility check is idempotent after first successful run."""
        fetch_calls = 0

        async def fake_fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:  # noqa: ARG001
            nonlocal fetch_calls
            if query.startswith("PRAGMA table_info(ticket_form_questions)"):
                fetch_calls += 1
                return [
                    {"name": "id"},
                    {"name": "step_id"},
                    {"name": "question_id"},
                    {"name": "label"},
                    {"name": "input_type"},
                    {"name": "options_json"},
                ]
            return []

        async def fake_execute(query: str, params: tuple[Any, ...] = ()) -> int:  # noqa: ARG001
            raise AssertionError("No ALTER TABLE should run when columns exist")

        monkeypatch.setattr(BaseRepository, "fetch_all", fake_fetch_all)
        monkeypatch.setattr(BaseRepository, "execute", fake_execute)

        await form_svc._ensure_question_schema_compatibility()
        await form_svc._ensure_question_schema_compatibility()

        assert fetch_calls == 1


# ---------------------------------------------------------------------------
# RouteExecutionContext
# ---------------------------------------------------------------------------


class TestRouteExecutionContext:
    """Tests for the RouteExecutionContext dataclass."""

    def test_add_answers(self) -> None:
        ctx = RouteExecutionContext(
            guild_id=1, user_id=2, category_id=3
        )
        ctx.add_answers(1, {
            "q1": {"answer": "test", "label": "Q1", "sort_order": 0},
        })
        assert "q1" in ctx.collected_answers
        assert ctx.collected_answers["q1"]["step"] == 1

    def test_is_expired(self) -> None:
        ctx = RouteExecutionContext(
            guild_id=1, user_id=2, category_id=3,
            expires_at=time.time() - 1,
        )
        assert ctx.is_expired() is True

    def test_is_not_expired(self) -> None:
        ctx = RouteExecutionContext(
            guild_id=1, user_id=2, category_id=3,
            expires_at=time.time() + 9999,
        )
        assert ctx.is_expired() is False

    def test_to_db_dict(self) -> None:
        ctx = RouteExecutionContext(
            guild_id=1, user_id=2, category_id=3,
            interaction_token="tok",
        )
        d = ctx.to_db_dict()
        assert d["guild_id"] == 1
        assert d["user_id"] == 2
        assert d["category_id"] == 3
        assert d["interaction_token"] == "tok"
        assert json.loads(d["collected_data"]) == {}

    def test_from_db_row(self) -> None:
        """Reconstruct from a dict-like row."""
        row = {
            "id": 42,
            "guild_id": 1,
            "user_id": 2,
            "category_id": 3,
            "current_step": 2,
            "collected_data": json.dumps({"q1": {"answer": "yes"}}),
            "interaction_token": "tok",
            "created_at": 1000,
            "expires_at": 2000,
        }
        ctx = RouteExecutionContext.from_db_row(row)
        assert ctx.session_id == 42
        assert ctx.guild_id == 1
        assert ctx.current_step == 2
        assert ctx.collected_answers == {"q1": {"answer": "yes"}}

    def test_add_answers_merges(self) -> None:
        """add_answers merges from multiple steps."""
        ctx = RouteExecutionContext(
            guild_id=1, user_id=2, category_id=3
        )
        ctx.add_answers(1, {"q1": {"answer": "a1", "label": "Q1"}})
        ctx.add_answers(2, {"q2": {"answer": "a2", "label": "Q2"}})
        assert len(ctx.collected_answers) == 2
        assert ctx.collected_answers["q1"]["step"] == 1
        assert ctx.collected_answers["q2"]["step"] == 2


# ---------------------------------------------------------------------------
# _validate_steps_rules (shared validation core)
# ---------------------------------------------------------------------------


class TestValidateStepsRules:
    """Tests for the DRY shared validation helper."""

    def test_empty_steps_valid(self) -> None:
        """No steps → no errors."""
        errors = TicketFormService._validate_steps_rules([])
        assert errors == []

    def test_too_many_steps(self) -> None:
        """Exceeding MAX_FORM_STEPS produces an error."""
        steps = [
            {"step_number": i, "questions": []}
            for i in range(1, MAX_FORM_STEPS + 2)
        ]
        errors = TicketFormService._validate_steps_rules(steps)
        assert any("steps" in e.lower() for e in errors)

    def test_duplicate_step_numbers(self) -> None:
        """Duplicate step numbers are caught."""
        steps = [
            {"step_number": 1, "questions": []},
            {"step_number": 1, "questions": []},
        ]
        errors = TicketFormService._validate_steps_rules(steps)
        assert any("duplicate" in e.lower() for e in errors)

    def test_too_many_questions_per_step(self) -> None:
        """More than MAX_QUESTIONS_PER_STEP triggers an error."""
        questions = [
            {"question_id": f"q{i}", "label": f"Q{i}", "input_type": "text"}
            for i in range(MAX_QUESTIONS_PER_STEP + 1)
        ]
        steps = [{"step_number": 1, "questions": questions}]
        errors = TicketFormService._validate_steps_rules(steps)
        assert any("questions" in e.lower() for e in errors)

    def test_non_text_input_type_is_invalid(self) -> None:
        """Any non-text input_type is invalid."""
        steps = [
            {
                "step_number": 1,
                "questions": [
                    {
                        "question_id": "q1",
                        "label": "Pick one",
                        "input_type": "select",
                        "options": [],
                    }
                ],
            }
        ]
        errors = TicketFormService._validate_steps_rules(steps)
        assert any("invalid input_type" in e for e in errors)

    def test_unknown_extra_fields_are_ignored(self) -> None:
        """Unknown step keys are ignored by validation."""
        steps = [
            {
                "step_number": 1,
                "questions": [
                    {"question_id": "q1", "label": "Q1", "input_type": "text"}
                ],
                "extra": {"a": 1},
            }
        ]
        errors = TicketFormService._validate_steps_rules(steps)
        assert errors == []

    def test_unknown_nested_step_fields_are_ignored(self) -> None:
        """Validation ignores irrelevant nested step fields."""
        steps = [
            {
                "step_number": 1,
                "questions": [
                    {"question_id": "q1", "label": "Q1", "input_type": "text"}
                ],
                "metadata": [{"anything": "ok"}],
            }
        ]
        errors = TicketFormService._validate_steps_rules(steps)
        assert errors == []

    def test_valid_form_no_errors(self) -> None:
        """A well-formed config produces no errors."""
        steps = [
            {
                "step_number": 1,
                "questions": [
                    {"question_id": "q1", "label": "Name", "input_type": "text"}
                ],
            },
            {
                "step_number": 2,
                "questions": [
                    {"question_id": "q2", "label": "Details", "input_type": "text"}
                ],
            },
        ]
        errors = TicketFormService._validate_steps_rules(steps)
        assert errors == []
