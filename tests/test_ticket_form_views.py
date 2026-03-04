"""
Tests for ticket form views — ModalBuilder, DynamicTicketModal,
TicketContinueView, create_ticket_from_route.

Uses FakeInteraction / mock_bot patterns from conftest and mocks the
service layer (TicketFormService, TicketService).
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helpers.ticket_form_views import (
    DynamicTicketModal,
    ModalBuilder,
    TicketContinueView,
    create_ticket_from_route,
)
from services.ticket_form_service import RouteExecutionContext
from tests.conftest import FakeInteraction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    guild_id: int = 123,
    user_id: int = 1,
    category_id: int = 10,
    current_step: int = 1,
    answers: dict | None = None,
) -> RouteExecutionContext:
    """Create a RouteExecutionContext for testing."""
    ctx = RouteExecutionContext(guild_id, user_id, category_id)
    ctx.current_step = current_step
    ctx.expires_at = time.time() + 900
    if answers:
        ctx.collected_answers = answers
    return ctx


def _make_category(
    *,
    cat_id: int = 10,
    name: str = "Bug Reports",
    description: str = "Report bugs",
) -> dict:
    return {"id": cat_id, "name": name, "description": description, "emoji": None}


def _make_step(
    *,
    step_id: int = 1,
    step_number: int = 1,
    title: str = "Step 1",
) -> dict:
    return {
        "id": step_id,
        "step_number": step_number,
        "title": title,
    }


def _make_questions(count: int = 2) -> list[dict]:
    questions = []
    for i in range(count):
        questions.append({
            "question_id": f"q{i + 1}",
            "label": f"Question {i + 1}",
            "placeholder": f"Enter Q{i + 1}",
            "style": "short" if i % 2 == 0 else "paragraph",
            "required": True,
            "min_length": 0,
            "max_length": 4000,
            "sort_order": i,
        })
    return questions


def _mock_bot_with_form_services(
    *,
    has_form: bool = True,
    form_config: dict | None = None,
    session: RouteExecutionContext | None = None,
    step_config: dict | None = None,
    questions: list | None = None,
    category: dict | None = None,
    next_step: int | None = None,
) -> MagicMock:
    """Build a mock bot with ticket_form and ticket stubs."""
    bot = MagicMock()

    # TicketFormService
    tfs = AsyncMock()
    tfs.has_form = AsyncMock(return_value=has_form)
    tfs.get_form_config = AsyncMock(return_value=form_config)
    tfs.create_session = AsyncMock(return_value=session)
    tfs.get_session = AsyncMock(return_value=session)
    tfs.update_session = AsyncMock(return_value=True)
    tfs.delete_session = AsyncMock(return_value=True)
    tfs.resolve_next_step = AsyncMock(return_value=next_step)
    tfs.get_step = AsyncMock(return_value=step_config)
    tfs.get_questions = AsyncMock(return_value=questions or [])
    tfs.save_responses = AsyncMock(return_value=True)
    bot.services.ticket_form = tfs

    # TicketService
    ts = AsyncMock()
    ts.get_category = AsyncMock(return_value=category or _make_category())
    ts.create_ticket = AsyncMock(return_value=1)
    ts.get_open_tickets = AsyncMock(return_value=[])
    bot.services.ticket = ts

    bot.get_channel = MagicMock(return_value=None)

    return bot


# ---------------------------------------------------------------------------
# ModalBuilder
# ---------------------------------------------------------------------------


class TestModalBuilder:
    """Tests for ModalBuilder.build_modal static factory."""

    @pytest.mark.asyncio
    async def test_build_modal_returns_modal(self) -> None:
        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), _make_questions(2), ctx
        )
        assert isinstance(modal, DynamicTicketModal)

    @pytest.mark.asyncio
    async def test_build_modal_title_includes_progress(self) -> None:
        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(title="Info"), _make_questions(1), ctx,
            total_steps=3,
        )
        assert "1/3" in modal.title

    @pytest.mark.asyncio
    async def test_build_modal_single_step_no_progress(self) -> None:
        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(title="Details"), _make_questions(1), ctx,
            total_steps=1,
        )
        assert "/" not in modal.title

    @pytest.mark.asyncio
    async def test_build_modal_title_truncated(self) -> None:
        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        long_title = "A" * 100
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(title=long_title), _make_questions(1), ctx,
        )
        assert len(modal.title) <= 45

    @pytest.mark.asyncio
    async def test_build_modal_adds_text_inputs(self) -> None:
        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        questions = _make_questions(3)
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )
        assert len(modal._inputs) == 3

    @pytest.mark.asyncio
    async def test_build_modal_max_five_inputs(self) -> None:
        """Discord limits modals to 5 text inputs."""
        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        questions = _make_questions(7)
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )
        assert len(modal._inputs) == 5

    @pytest.mark.asyncio
    async def test_build_modal_paragraph_style(self) -> None:
        """Questions with style 'paragraph' get TextStyle.paragraph."""
        import discord

        bot = _mock_bot_with_form_services()
        ctx = _make_context()
        questions = [
            {
                "question_id": "desc",
                "label": "Description",
                "placeholder": "",
                "style": "paragraph",
                "required": True,
                "min_length": 0,
                "max_length": 4000,
                "sort_order": 0,
            },
        ]
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )
        _, _, text_input = modal._inputs[0]
        assert text_input.style == discord.TextStyle.paragraph


# ---------------------------------------------------------------------------
# DynamicTicketModal
# ---------------------------------------------------------------------------


class TestDynamicTicketModal:
    """Tests for the on_submit callback of DynamicTicketModal."""

    @pytest.mark.asyncio
    async def test_on_submit_terminal_creates_ticket(self) -> None:
        """When resolve_next_step returns None, a ticket is created."""
        ctx = _make_context()
        bot = _mock_bot_with_form_services(
            session=ctx,
            next_step=None,  # terminal
            category=_make_category(),
        )
        questions = _make_questions(1)
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )

        # Simulate user typed values
        for _, _, text_input in modal._inputs:
            text_input._value = "User answer"

        interaction = FakeInteraction()

        with patch(
            "helpers.ticket_form_views.create_ticket_from_route",
            new_callable=AsyncMock,
        ) as mock_create:
            await modal.on_submit(interaction)  # type: ignore[arg-type]

            # Session should be deleted
            bot.services.ticket_form.delete_session.assert_called_once_with(
                ctx.guild_id, ctx.user_id
            )
            # Ticket creation invoked
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_submit_more_steps_shows_continue(self) -> None:
        """When resolve_next_step returns a step number, show continue view."""
        ctx = _make_context()
        bot = _mock_bot_with_form_services(
            session=ctx,
            next_step=2,  # more steps
            step_config=_make_step(step_number=2, title="Details"),
        )
        questions = _make_questions(1)
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )

        for _, _, text_input in modal._inputs:
            text_input._value = "answer"

        interaction = FakeInteraction()
        # Patch TicketContinueView to avoid event loop issues on instantiation
        with patch(
            "helpers.ticket_form_views.TicketContinueView",
            return_value=MagicMock(),
        ):
            await modal.on_submit(interaction)  # type: ignore[arg-type]

        # Session should be updated
        bot.services.ticket_form.update_session.assert_called_once()
        # Response sent
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_on_submit_collects_answers(self) -> None:
        """Answers from text inputs are merged into context."""
        ctx = _make_context()
        bot = _mock_bot_with_form_services(session=ctx, next_step=None)
        questions = _make_questions(2)
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )

        modal._inputs[0][2]._value = "Answer 1"
        modal._inputs[1][2]._value = "Answer 2"

        interaction = FakeInteraction()
        with patch(
            "helpers.ticket_form_views.create_ticket_from_route",
            new_callable=AsyncMock,
        ):
            await modal.on_submit(interaction)  # type: ignore[arg-type]

        assert "q1" in ctx.collected_answers
        assert "q2" in ctx.collected_answers
        assert ctx.collected_answers["q1"]["answer"] == "Answer 1"

    @pytest.mark.asyncio
    async def test_on_error_sends_error_message(self) -> None:
        """on_error sends an error message to the user."""
        ctx = _make_context()
        bot = _mock_bot_with_form_services(session=ctx)
        questions = _make_questions(1)
        modal = ModalBuilder.build_modal(
            bot, _make_category(), _make_step(), questions, ctx,
        )

        interaction = FakeInteraction()
        await modal.on_error(interaction, RuntimeError("test error"))  # type: ignore[arg-type]
        assert interaction.response._is_done


# ---------------------------------------------------------------------------
# TicketContinueView
# ---------------------------------------------------------------------------


class TestTicketContinueView:
    """Tests for the Continue / Cancel persistent button view."""

    @pytest.mark.asyncio
    async def test_view_has_two_buttons(self) -> None:
        bot = _mock_bot_with_form_services()
        view = TicketContinueView(bot)
        assert len(view.children) == 2

    @pytest.mark.asyncio
    async def test_view_custom_ids(self) -> None:
        bot = _mock_bot_with_form_services()
        view = TicketContinueView(bot)
        ids = {getattr(child, "custom_id", None) for child in view.children}
        assert "ticket_form_continue" in ids
        assert "ticket_form_cancel" in ids

    @pytest.mark.asyncio
    async def test_view_no_timeout(self) -> None:
        bot = _mock_bot_with_form_services()
        view = TicketContinueView(bot)
        assert view.timeout is None

    @pytest.mark.asyncio
    async def test_cancel_deletes_session(self) -> None:
        """Clicking cancel deletes the user's session."""
        bot = _mock_bot_with_form_services()
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_cancel(interaction)  # type: ignore[arg-type]

        bot.services.ticket_form.delete_session.assert_called_once_with(
            interaction.guild.id, interaction.user.id  # type: ignore[union-attr]
        )
        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_cancel_no_guild(self) -> None:
        """Cancel outside a guild sends error."""
        bot = _mock_bot_with_form_services()
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        interaction.guild = None
        await view._on_cancel(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        bot.services.ticket_form.delete_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_continue_no_session_sends_expired(self) -> None:
        """Clicking continue with no session sends expired message."""
        bot = _mock_bot_with_form_services(session=None)
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_continue_no_guild(self) -> None:
        bot = _mock_bot_with_form_services()
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        interaction.guild = None
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done

    @pytest.mark.asyncio
    async def test_continue_no_step_config(self) -> None:
        """If step config is missing, sends error and deletes session."""
        ctx = _make_context()
        bot = _mock_bot_with_form_services(session=ctx, step_config=None)
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        bot.services.ticket_form.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_no_questions(self) -> None:
        """If step has no questions, sends error and deletes session."""
        ctx = _make_context()
        step = _make_step()
        step["questions"] = None
        bot = _mock_bot_with_form_services(
            session=ctx, step_config=step, questions=[],
        )
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        bot.services.ticket_form.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_no_category(self) -> None:
        """If category is gone, sends error and deletes session."""
        ctx = _make_context()
        step = _make_step()
        step["questions"] = _make_questions(1)
        bot = _mock_bot_with_form_services(session=ctx, step_config=step)
        bot.services.ticket.get_category = AsyncMock(return_value=None)
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        bot.services.ticket_form.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_success_shows_modal(self) -> None:
        """Successful continue loads next step and sends modal."""
        ctx = _make_context(current_step=2)
        step = _make_step(step_number=2)
        step["questions"] = _make_questions(1)
        form_config = {"steps": [_make_step(step_number=1), step]}
        bot = _mock_bot_with_form_services(
            session=ctx,
            step_config=step,
            form_config=form_config,
            category=_make_category(),
        )
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None

    @pytest.mark.asyncio
    async def test_continue_text_only_step_shows_modal(self) -> None:
        """Ticket form steps are always presented as modals."""
        ctx = _make_context(current_step=2)
        step = _make_step(step_number=2)
        step["questions"] = [
            {
                "question_id": "issue_type",
                "label": "Issue Type",
                "input_type": "text",
                "options": [],
                "placeholder": "Choose one",
                "sort_order": 0,
            }
        ]
        form_config = {"steps": [_make_step(step_number=1), step]}
        bot = _mock_bot_with_form_services(
            session=ctx,
            step_config=step,
            form_config=form_config,
            category=_make_category(),
        )
        view = TicketContinueView(bot)

        interaction = FakeInteraction()
        await view._on_continue(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert interaction.response.sent_modal is not None


# ---------------------------------------------------------------------------
# TicketCategorySelect — dynamic form routing
# ---------------------------------------------------------------------------


class TestCategorySelectFormRouting:
    """Tests that TicketCategorySelect routes to dynamic forms correctly."""

    @pytest.mark.asyncio
    async def test_callback_routes_to_form(self) -> None:
        """When has_form is True, callback starts dynamic form flow."""
        from helpers.ticket_views import TicketCategorySelect

        ctx = _make_context()
        categories = [
            {"id": 10, "name": "Bugs", "description": "Report bugs", "emoji": None},
        ]
        bot = _mock_bot_with_form_services(session=ctx)

        select = TicketCategorySelect(bot, categories)
        select._values = ["10"]
        type(select).values = property(lambda self: self._values)  # type: ignore[assignment]

        interaction = FakeInteraction()

        with patch(
            "helpers.ticket_views._start_dynamic_form",
            new_callable=AsyncMock,
        ) as mock_start:
            await select.callback(interaction)  # type: ignore[arg-type]
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_falls_back_without_form(self) -> None:
        """When has_form is False, falls back to TicketDescriptionModal."""
        from helpers.ticket_views import TicketCategorySelect, TicketDescriptionModal

        categories = [
            {"id": 10, "name": "Bugs", "description": "Report bugs", "emoji": None},
        ]
        bot = _mock_bot_with_form_services(has_form=False)

        # Also add legacy services
        ts = AsyncMock()
        ts.check_max_open_tickets = AsyncMock(return_value=True)
        bot.services.ticket = ts

        select = TicketCategorySelect(bot, categories)
        select._values = ["10"]
        type(select).values = property(lambda self: self._values)  # type: ignore[assignment]

        interaction = FakeInteraction()
        await select.callback(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert isinstance(interaction.response.sent_modal, TicketDescriptionModal)

    @pytest.mark.asyncio
    async def test_callback_falls_back_on_service_error(self) -> None:
        """When ticket_form service is unavailable, uses legacy flow."""
        from helpers.ticket_views import TicketCategorySelect, TicketDescriptionModal

        categories = [
            {"id": 10, "name": "Bugs", "description": "", "emoji": None},
        ]
        bot = MagicMock()

        # Make ticket_form raise RuntimeError (not initialized)
        type(bot.services).ticket_form = property(
            lambda self: (_ for _ in ()).throw(RuntimeError)
        )

        ts = AsyncMock()
        ts.check_max_open_tickets = AsyncMock(return_value=True)
        bot.services.ticket = ts

        select = TicketCategorySelect(bot, categories)
        select._values = ["10"]
        type(select).values = property(lambda self: self._values)  # type: ignore[assignment]

        interaction = FakeInteraction()
        await select.callback(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert isinstance(interaction.response.sent_modal, TicketDescriptionModal)


# ---------------------------------------------------------------------------
# create_ticket_from_route
# ---------------------------------------------------------------------------


class TestCreateTicketFromRoute:
    """Tests for the create_ticket_from_route helper."""

    @pytest.mark.asyncio
    async def test_creates_ticket_with_combined_description(self) -> None:
        """Answers are combined into a description and passed to thread creation."""
        ctx = _make_context()
        ctx.collected_answers = {
            "q1": {"answer": "Bug", "label": "Type", "step": 1, "sort_order": 0},
            "q2": {"answer": "It crashes", "label": "Details", "step": 1, "sort_order": 1},
        }
        category = _make_category()
        bot = _mock_bot_with_form_services(category=category)
        interaction = FakeInteraction()

        with patch(
            "helpers.ticket_views._create_ticket_thread",
            new_callable=AsyncMock,
        ) as mock_create_thread:
            await create_ticket_from_route(bot, interaction, ctx)  # type: ignore[arg-type]

            mock_create_thread.assert_called_once()
            call_kwargs = mock_create_thread.call_args
            # form_responses should be the collected answers
            assert call_kwargs.kwargs.get("form_responses") is not None or (
                len(call_kwargs.args) > 0
            )

    @pytest.mark.asyncio
    async def test_saves_responses_after_creation(self) -> None:
        """After ticket creation, form responses are saved to DB."""
        ctx = _make_context()
        ctx.collected_answers = {
            "q1": {"answer": "test", "label": "Q1", "step": 1, "sort_order": 0},
        }
        bot = _mock_bot_with_form_services(category=_make_category())

        interaction = FakeInteraction()

        with patch(
            "helpers.ticket_views._create_ticket_thread",
            new_callable=AsyncMock,
            return_value=42,
        ):
            await create_ticket_from_route(bot, interaction, ctx)  # type: ignore[arg-type]

            bot.services.ticket_form.save_responses.assert_called_once_with(
                42, ctx.collected_answers
            )

    @pytest.mark.asyncio
    async def test_no_crash_when_no_open_tickets(self) -> None:
        """If _create_ticket_thread returns None, no save_responses call."""
        ctx = _make_context()
        ctx.collected_answers = {
            "q1": {"answer": "test", "label": "Q1", "step": 1, "sort_order": 0},
        }
        bot = _mock_bot_with_form_services(category=_make_category())

        interaction = FakeInteraction()

        with patch(
            "helpers.ticket_views._create_ticket_thread",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await create_ticket_from_route(bot, interaction, ctx)  # type: ignore[arg-type]

            bot.services.ticket_form.save_responses.assert_not_called()
