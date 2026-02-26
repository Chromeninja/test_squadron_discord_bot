"""
Ticket form configuration API endpoints.

Provides CRUD for per-category form steps and questions, form
validation, and retrieval of per-ticket form responses.
"""

from __future__ import annotations

from core.dependencies import (
    get_ticket_form_service,
    get_ticket_service,
    require_discord_manager,
    require_staff,
)
from core.schemas import (
    TicketFormBranchRule,
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

from services.ticket_form_service import TicketFormService
from services.ticket_service import TicketService
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_guild_category(
    svc: TicketService, category_id: int, guild_id: int
) -> dict:
    """Verify a category exists and belongs to the given guild.

    Raises ``HTTPException(404)`` on mismatch.
    """
    cat = await svc.get_category(category_id)
    if cat is None or cat["guild_id"] != guild_id:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat


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
                    branch_rules=[
                        TicketFormBranchRule(
                            question_id=r.get("question_id", ""),
                            match_pattern=r.get("match_pattern", ""),
                            next_step_number=r.get("next_step_number"),
                        )
                        for r in s.get("branch_rules", [])
                    ],
                    default_next_step=s.get("default_next_step"),
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
    svc: TicketService = Depends(get_ticket_service),
    form_svc: TicketFormService = Depends(get_ticket_form_service),
) -> TicketFormConfigResponse:
    """Get the full form configuration for a ticket category."""
    guild_id = ensure_active_guild(current_user)
    await _require_guild_category(svc, category_id, guild_id)
    config = await form_svc.get_form_config(category_id)
    return _build_form_response(category_id, config)


@router.put(
    "/categories/{category_id}/form",
    response_model=TicketFormConfigResponse,
)
async def replace_form_config(
    category_id: int,
    body: TicketFormConfigUpdate,
    current_user: UserProfile = Depends(require_discord_manager()),
    svc: TicketService = Depends(get_ticket_service),
    form_svc: TicketFormService = Depends(get_ticket_form_service),
) -> TicketFormConfigResponse:
    """Replace the entire form config for a category (atomic)."""
    guild_id = ensure_active_guild(current_user)
    await _require_guild_category(svc, category_id, guild_id)

    # Convert to plain dicts for the service
    steps_data = [
        {
            "step_number": s.step_number,
            "title": s.title,
            "branch_rules": [r.model_dump() for r in s.branch_rules],
            "default_next_step": s.default_next_step,
            "questions": [q.model_dump() for q in s.questions],
        }
        for s in body.steps
    ]

    payload_errors = form_svc.validate_form_payload(steps_data)
    if payload_errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid form config", "errors": payload_errors},
        )

    success = await form_svc.replace_form_config(category_id, steps_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save form config")

    # Return the updated config
    return await get_form_config(category_id, current_user, svc, form_svc)


@router.delete(
    "/categories/{category_id}/form",
    response_model=TicketFormConfigResponse,
)
async def delete_form_config(
    category_id: int,
    current_user: UserProfile = Depends(require_discord_manager()),
    svc: TicketService = Depends(get_ticket_service),
    form_svc: TicketFormService = Depends(get_ticket_form_service),
) -> TicketFormConfigResponse:
    """Delete all form config for a category (reverts to legacy modal)."""
    guild_id = ensure_active_guild(current_user)
    await _require_guild_category(svc, category_id, guild_id)

    await form_svc.delete_form_config(category_id)

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
    svc: TicketService = Depends(get_ticket_service),
    form_svc: TicketFormService = Depends(get_ticket_form_service),
) -> TicketFormValidation:
    """Validate the form configuration for a category."""
    guild_id = ensure_active_guild(current_user)
    await _require_guild_category(svc, category_id, guild_id)

    errors = await form_svc.validate_form(category_id)

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
    svc: TicketService = Depends(get_ticket_service),
    form_svc: TicketFormService = Depends(get_ticket_form_service),
) -> TicketFormResponseList:
    """Get form responses for a specific ticket."""
    guild_id = ensure_active_guild(current_user)

    # Verify the ticket belongs to this guild via single-row lookup
    ticket = await svc.get_ticket_by_id(ticket_id, guild_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    responses = await form_svc.get_responses(ticket_id)

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
