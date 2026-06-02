"""Internal API routes for ticket forms — DB-backed, API key protected.

These routes provide CRUD operations on form steps, questions, sessions,
and responses, accessed by the bot connector and tested with mocked repositories.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.api_key import require_bot_api_key
from backend.db.repository.ticket_forms import TicketFormRepository

router = APIRouter(prefix="/internal", tags=["internal-ticket-forms"])
logger = logging.getLogger(__name__)


def get_ticket_form_repository() -> TicketFormRepository:
    """Provide a TicketFormRepository. Override in tests via dependency_overrides.

    The repository is stateless, so a fresh instance per request is cheap.
    """
    return TicketFormRepository()


# ------------------------------------------------------------------
# Form Configuration: get/replace/delete/validate
# ------------------------------------------------------------------


@router.get("/guilds/{guild_id}/ticket-forms/config/{category_id}")
async def get_form_config(
    guild_id: int,
    category_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Return the full form configuration tree for a category."""
    config = await repo.get_form_config(category_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No form configured for this category")
    return {"config": config}


@router.put("/guilds/{guild_id}/ticket-forms/config/{category_id}")
async def replace_form_config(
    guild_id: int,
    category_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Atomically replace the entire form config for a category.

    Expects payload with ``steps`` key: list of step dicts with
    ``step_number``, ``title``, and ``questions`` list.
    """
    steps_data = payload.get("steps", [])
    success = await repo.replace_form_config(category_id, steps_data)
    if not success:
        raise HTTPException(
            status_code=422, detail="Failed to replace form config"
        )
    return {"success": True}


@router.delete("/guilds/{guild_id}/ticket-forms/config/{category_id}")
async def delete_form_config(
    guild_id: int,
    category_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Delete all form steps for a category."""
    success = await repo.delete_form_config(category_id)
    return {"success": success}


@router.post("/guilds/{guild_id}/ticket-forms/validate/{category_id}")
async def validate_form(
    guild_id: int,
    category_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Validate the form configuration for a category.

    Returns list of error strings; empty list means valid.
    """
    errors = await repo.validate_form(category_id)
    return {"valid": len(errors) == 0, "errors": errors}


# ------------------------------------------------------------------
# Form Steps CRUD
# ------------------------------------------------------------------


@router.post("/guilds/{guild_id}/ticket-forms/steps")
async def create_step(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Create a new form step.

    Requires ``category_id`` and ``step_number``. Optional: ``title``.
    """
    category_id = payload.get("category_id")
    step_number = payload.get("step_number")
    if category_id is None or step_number is None:
        raise HTTPException(
            status_code=422,
            detail="Missing category_id or step_number",
        )
    title = payload.get("title", "")
    step_id = await repo.create_step(category_id, step_number, title)
    if step_id is None:
        raise HTTPException(
            status_code=422, detail="Failed to create step"
        )
    return {"step_id": step_id}


@router.get("/guilds/{guild_id}/ticket-forms/steps/{category_id}")
async def get_steps(
    guild_id: int,
    category_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Return all form steps for a category."""
    steps = await repo.get_steps(category_id)
    return {"steps": steps}


@router.patch("/guilds/{guild_id}/ticket-forms/steps/{step_id}")
async def update_step(
    guild_id: int,
    step_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Update fields on a form step."""
    success = await repo.update_step(step_id, **payload)
    if not success:
        raise HTTPException(status_code=404, detail="Step not found or no updates")
    return {"success": success}


@router.delete("/guilds/{guild_id}/ticket-forms/steps/{step_id}")
async def delete_step(
    guild_id: int,
    step_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Delete a form step."""
    success = await repo.delete_step(step_id)
    if not success:
        raise HTTPException(status_code=404, detail="Step not found")
    return {"success": True}


# ------------------------------------------------------------------
# Form Questions CRUD
# ------------------------------------------------------------------


@router.post("/guilds/{guild_id}/ticket-forms/questions")
async def create_question(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Create a new form question.

    Requires ``step_id``, ``question_id``, ``label``.
    """
    step_id = payload.get("step_id")
    question_id = payload.get("question_id")
    label = payload.get("label")
    if step_id is None or question_id is None or label is None:
        raise HTTPException(
            status_code=422,
            detail="Missing step_id, question_id, or label",
        )
    qid = await repo.create_question(
        step_id,
        question_id,
        label,
        input_type=payload.get("input_type", "text"),
        placeholder=payload.get("placeholder", ""),
        style=payload.get("style", "short"),
        required=payload.get("required", True),
        min_length=payload.get("min_length"),
        max_length=payload.get("max_length"),
        sort_order=payload.get("sort_order", 0),
    )
    if qid is None:
        raise HTTPException(status_code=422, detail="Failed to create question")
    return {"question_id": qid}


@router.get("/guilds/{guild_id}/ticket-forms/questions/{step_id}")
async def get_questions(
    guild_id: int,
    step_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Return all questions for a step."""
    questions = await repo.get_questions(step_id)
    return {"questions": questions}


@router.patch("/guilds/{guild_id}/ticket-forms/questions/{question_id}")
async def update_question(
    guild_id: int,
    question_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Update fields on a form question."""
    success = await repo.update_question(question_id, **payload)
    if not success:
        raise HTTPException(
            status_code=404, detail="Question not found or no updates"
        )
    return {"success": success}


@router.delete("/guilds/{guild_id}/ticket-forms/questions/{question_id}")
async def delete_question(
    guild_id: int,
    question_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Delete a form question."""
    success = await repo.delete_question(question_id)
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"success": True}


# ------------------------------------------------------------------
# Route Sessions
# ------------------------------------------------------------------


@router.post("/guilds/{guild_id}/ticket-forms/sessions")
async def create_session(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Create a new route session.

    Requires ``user_id`` and ``category_id``.
    """
    user_id = payload.get("user_id")
    category_id = payload.get("category_id")
    if user_id is None or category_id is None:
        raise HTTPException(
            status_code=422, detail="Missing user_id or category_id"
        )
    session = await repo.create_session(
        guild_id,
        user_id,
        category_id,
        interaction_token=payload.get("interaction_token"),
        is_public=payload.get("is_public", False),
    )
    return {"session": session}


@router.get("/guilds/{guild_id}/ticket-forms/sessions/{user_id}")
async def get_session(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Retrieve an active route session for a user."""
    session = await repo.get_session(guild_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.patch("/guilds/{guild_id}/ticket-forms/sessions/{user_id}")
async def update_session(
    guild_id: int,
    user_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Update a session with new step and answers.

    Expects ``step`` and ``answers`` keys.
    """
    step = payload.get("step")
    answers = payload.get("answers", {})
    if step is None:
        raise HTTPException(status_code=422, detail="Missing step")
    success = await repo.update_session(
        guild_id,
        user_id,
        step,
        answers,
        interaction_token=payload.get("interaction_token"),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@router.delete("/guilds/{guild_id}/ticket-forms/sessions/{user_id}")
async def delete_session(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Delete a route session."""
    success = await repo.delete_session(guild_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


# ------------------------------------------------------------------
# Form Responses
# ------------------------------------------------------------------


@router.post("/guilds/{guild_id}/ticket-forms/responses/{ticket_id}")
async def save_responses(
    guild_id: int,
    ticket_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Batch-insert form responses for a completed ticket.

    Expects ``collected_answers`` key mapping question_id → answer dict.
    """
    collected_answers = payload.get("collected_answers", {})
    success = await repo.save_responses(ticket_id, collected_answers)
    return {"success": success}


@router.get("/guilds/{guild_id}/ticket-forms/responses/{ticket_id}")
async def get_responses(
    guild_id: int,
    ticket_id: int,
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Return all form responses for a ticket."""
    responses = await repo.get_responses(ticket_id)
    return {"responses": responses}


@router.delete("/ticket-forms/sessions/expired")
async def cleanup_expired_sessions(
    _: str = Depends(require_bot_api_key),
    repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> dict[str, Any]:
    """Delete all expired route sessions (global cleanup); returns count deleted."""
    deleted = await repo.cleanup_expired_sessions()
    return {"deleted": deleted}
