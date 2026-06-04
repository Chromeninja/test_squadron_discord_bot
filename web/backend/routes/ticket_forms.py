"""
Ticket form configuration API endpoints.

Provides CRUD for per-category form steps and questions, form
validation, and retrieval of per-ticket form responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.dependencies import (
    get_ticket_form_repository,
    get_ticket_repository,
    require_discord_manager,
    require_staff,
)
from core.schemas import (
    TicketFormConfig,
    TicketFormConfigResponse,
    TicketFormConfigUpdate,
    TicketFormQuestion,
    TicketFormResponse,
    TicketFormResponseList,
    TicketFormStep,
    TicketFormValidation,
    UserProfile,
)
from core.validation import ensure_active_guild
from fastapi import APIRouter, Depends, HTTPException

from utils.logging import get_logger
from web.backend.routes._ticket_helpers import require_guild_category

if TYPE_CHECKING:
    from backend.db.repository.ticket_forms import TicketFormRepository
    from backend.db.repository.tickets import TicketRepository

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_form_response(
    category_id: int, config: dict | None
) -> TicketFormConfigResponse:
    """Build a ``TicketFormConfigResponse`` from a service config dict."""
    if config is None:
        return TicketFormConfigResponse(
            config=TicketFormConfig(category_id=category_id, steps=[])
        )

    return TicketFormConfigResponse(
        config=TicketFormConfig(
            category_id=category_id,
            steps=[
                TicketFormStep(
                    id=s["id"],
                    step_number=s["step_number"],
                    title=s["title"],
                    questions=[
                        TicketFormQuestion(
                            id=q["id"],
                            question_id=q["question_id"],
                            label=q["label"],
                            input_type=q.get("input_type", "text"),
                            options=q.get("options", []),
                            placeholder=q["placeholder"],
                            style=q["style"],
                            required=q["required"],
                            min_length=q["min_length"],
                            max_length=q["max_length"],
                            sort_order=q["sort_order"],
                        )
                        for q in s.get("questions", [])
                    ],
                )
                for s in config.get("steps", [])
            ],
        )
    )


# ---------------------------------------------------------------------------
# Form Config CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/categories/{category_id}/form",
    response_model=TicketFormConfigResponse,
)
async def get_form_config(
    category_id: int,
    current_user: UserProfile = Depends(require_staff()),
    repo: TicketRepository = Depends(get_ticket_repository),
    form_repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> TicketFormConfigResponse:
    """Get the full form configuration for a ticket category."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(repo, category_id, guild_id)
    config = await form_repo.get_form_config(category_id)
    return _build_form_response(category_id, config)


@router.put(
    "/categories/{category_id}/form",
    response_model=TicketFormConfigResponse,
)
async def replace_form_config(
    category_id: int,
    body: TicketFormConfigUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
    form_repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> TicketFormConfigResponse:
    """Replace the entire form config for a category (atomic)."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(repo, category_id, guild_id)

    # Convert to plain dicts for the service
    steps_data = [
        {
            "step_number": s.step_number,
            "title": s.title,
            "questions": [q.model_dump() for q in s.questions],
        }
        for s in body.steps
    ]

    payload_errors = form_repo.validate_form_payload(steps_data)
    if payload_errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid form config", "errors": payload_errors},
        )

    success = await form_repo.replace_form_config(category_id, steps_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save form config")

    # Return the updated config
    return await get_form_config(category_id, current_user, repo, form_repo)


@router.delete(
    "/categories/{category_id}/form",
    response_model=TicketFormConfigResponse,
)
async def delete_form_config(
    category_id: int,
    current_user: UserProfile = Depends(require_discord_manager()),
    repo: TicketRepository = Depends(get_ticket_repository),
    form_repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> TicketFormConfigResponse:
    """Delete all form config for a category (reverts to legacy modal)."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(repo, category_id, guild_id)

    await form_repo.delete_form_config(category_id)

    return _build_form_response(category_id, None)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@router.get(
    "/categories/{category_id}/form/validate",
    response_model=TicketFormValidation,
)
async def validate_form_config(
    category_id: int,
    current_user: UserProfile = Depends(require_staff()),
    repo: TicketRepository = Depends(get_ticket_repository),
    form_repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> TicketFormValidation:
    """Validate the form configuration for a category."""
    guild_id = ensure_active_guild(current_user)
    await require_guild_category(repo, category_id, guild_id)

    errors = await form_repo.validate_form(category_id)

    return TicketFormValidation(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Form Responses
# ---------------------------------------------------------------------------


@router.get(
    "/{ticket_id}/responses",
    response_model=TicketFormResponseList,
)
async def get_ticket_responses(
    ticket_id: int,
    current_user: UserProfile = Depends(require_staff()),
    repo: TicketRepository = Depends(get_ticket_repository),
    form_repo: TicketFormRepository = Depends(get_ticket_form_repository),
) -> TicketFormResponseList:
    """Get form responses for a specific ticket."""
    guild_id = ensure_active_guild(current_user)

    # Verify the ticket belongs to this guild via single-row lookup
    ticket = await repo.get_ticket(guild_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    responses = await form_repo.get_responses(ticket_id)

    return TicketFormResponseList(
        responses=[
            TicketFormResponse(
                question_id=r["question_id"],
                question_label=r["question_label"],
                answer=r["answer"],
                step_number=r["step_number"],
                sort_order=r["sort_order"],
            )
            for r in responses
        ]
    )
