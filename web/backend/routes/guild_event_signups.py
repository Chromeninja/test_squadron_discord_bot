"""Dashboard-facing event signup, roster, export, and messaging routes.

Regular authenticated guild members may mark interest, sign up for roles, and
view role state for active/upcoming/recurring events. Coordinator-only actions
(roster, manual assignment, CSV export, channel messaging) require
event_coordinator or higher. All permissions are enforced server-side; the
EventSignupService is the single choke point for the business rules.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import TYPE_CHECKING

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_event_coordinator,
    require_guild_permission,
    translate_internal_api_error,
)
from core.event_signup_service import (
    EventRolesState,
    EventRoleView,
    EventRosterRoleState,
    EventRosterState,
    EventRosterUserState,
    EventSignupService,
    SignupError,
    SignupState,
    get_event_signup_service,
)
from core.role_utils import is_event_coordinator
from core.schemas import (
    EventMessageRequest,
    EventMessageResponse,
    EventRoleSchema,
    EventRoleSignupRequest,
    EventRolesResponse,
    EventRosterResponse,
    EventRosterRole,
    EventRosterUser,
    EventSignupResponse,
    UserProfile,
)
from core.validation import ensure_guild_match
from fastapi import APIRouter, Body, Depends, HTTPException, Response

if TYPE_CHECKING:
    from collections.abc import Awaitable

router = APIRouter(prefix="/api/guilds", tags=["guild-event-signups"])
logger = logging.getLogger(__name__)

# Shared alias so call sites read naturally.
is_coordinator = is_event_coordinator


async def _guard[T](awaitable: Awaitable[T]) -> T:
    """Run a service coroutine, mapping SignupError to an HTTPException."""
    try:
        return await awaitable
    except SignupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _signup_response(state: SignupState) -> EventSignupResponse:
    """Map the service signup contract to the public API schema."""
    return EventSignupResponse(
        event_id=state["event_id"],
        signed_up=state["signed_up"],
        web_signup_count=state["web_signup_count"],
    )


def _role_schema(role: EventRoleView) -> EventRoleSchema:
    """Map one service role record to the public API schema."""
    return EventRoleSchema(
        id=role["id"],
        event_id=role["event_id"],
        name=role["name"],
        emoji=role["emoji"],
        description=role["description"],
        capacity=role["capacity"],
        sort_order=role["sort_order"],
        locked=role["locked"],
        signup_count=role["signup_count"],
        current_user_signed_up=role["current_user_signed_up"],
    )


def _roles_response(state: EventRolesState) -> EventRolesResponse:
    """Map the service role-list contract to the public API schema."""
    return EventRolesResponse(
        roles=[_role_schema(role) for role in state["roles"]],
        allow_multiple_roles=state["allow_multiple_roles"],
        signups_enabled=state["signups_enabled"],
        signups_closed=state["signups_closed"],
    )


def _roster_user_schema(user: EventRosterUserState) -> EventRosterUser:
    """Map one service roster member to the public API schema."""
    return EventRosterUser(
        user_id=user["user_id"],
        display_name=user["display_name"],
        created_at=user["created_at"],
    )


def _roster_role_schema(role: EventRosterRoleState) -> EventRosterRole:
    """Map one service roster role to the public API schema."""
    return EventRosterRole(
        role_id=role["role_id"],
        name=role["name"],
        emoji=role["emoji"],
        capacity=role["capacity"],
        locked=role["locked"],
        users=[_roster_user_schema(user) for user in role["users"]],
    )


def _roster_response(state: EventRosterState) -> EventRosterResponse:
    """Map the service roster contract to the public API schema."""
    return EventRosterResponse(
        event_id=state["event_id"],
        total_web_signups=state["total_web_signups"],
        no_role_users=[
            _roster_user_schema(user) for user in state["no_role_users"]
        ],
        roles=[_roster_role_schema(role) for role in state["roles"]],
        discord_user_count=state["discord_user_count"],
    )


# ---------------------------------------------------------------------------
# Per-user write rate limiting
# ---------------------------------------------------------------------------
# SQLite serializes writes, so member signup writes are kept bounded per user
# to protect the DB (and Discord sync churn) from click-spam under high
# concurrency. In-process sliding window: cheap, no new dependency, and with
# multiple workers each process allows the full quota — acceptable slack for
# an anti-abuse guard. Reads are never limited.
_WRITE_RATE_LIMIT_MAX = 10
_WRITE_RATE_LIMIT_WINDOW_SECONDS = 10.0
_write_rate_buckets: dict[str, deque[float]] = {}


def _enforce_signup_write_rate_limit(user_id: str) -> None:
    """Raise 429 when a user exceeds the signup-write budget for the window."""
    now = time.monotonic()
    bucket = _write_rate_buckets.setdefault(user_id, deque())
    while bucket and now - bucket[0] > _WRITE_RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _WRITE_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many signup changes; wait a few seconds and try again.",
        )
    bucket.append(now)
    # Keep the map from accumulating idle users indefinitely.
    if len(_write_rate_buckets) > 50_000:
        cutoff = now - _WRITE_RATE_LIMIT_WINDOW_SECONDS
        stale = [u for u, b in _write_rate_buckets.items() if not b or b[-1] < cutoff]
        for uid in stale:
            _write_rate_buckets.pop(uid, None)


def _reset_signup_write_rate_limits() -> None:
    """Test hook: clear all rate-limit state."""
    _write_rate_buckets.clear()


# ---------------------------------------------------------------------------
# Regular member: whole-event interest
# ---------------------------------------------------------------------------
@router.post(
    "/{guild_id}/events/{event_id}/signup",
    response_model=EventSignupResponse,
    status_code=201,
)
async def mark_interest(
    guild_id: int,
    event_id: int,
    current_user: UserProfile = Depends(require_guild_permission("user")),
    service: EventSignupService = Depends(get_event_signup_service),
):
    """Mark whole-event interest for the current user."""
    ensure_guild_match(guild_id, current_user)
    _enforce_signup_write_rate_limit(current_user.user_id)
    state = await _guard(
        service.mark_interest(
            guild_id,
            event_id,
            current_user.user_id,
            is_coordinator=is_coordinator(current_user),
        )
    )
    return _signup_response(state)


@router.delete(
    "/{guild_id}/events/{event_id}/signup",
    response_model=EventSignupResponse,
)
async def withdraw_interest(
    guild_id: int,
    event_id: int,
    current_user: UserProfile = Depends(require_guild_permission("user")),
    service: EventSignupService = Depends(get_event_signup_service),
):
    """Withdraw whole-event interest (hard delete) for the current user."""
    ensure_guild_match(guild_id, current_user)
    _enforce_signup_write_rate_limit(current_user.user_id)
    state = await _guard(
        service.withdraw_interest(
            guild_id,
            event_id,
            current_user.user_id,
            is_coordinator=is_coordinator(current_user),
        )
    )
    return _signup_response(state)


# ---------------------------------------------------------------------------
# Regular member: role list + role signup
# ---------------------------------------------------------------------------
@router.get(
    "/{guild_id}/events/{event_id}/roles",
    response_model=EventRolesResponse,
)
async def list_event_roles(
    guild_id: int,
    event_id: int,
    current_user: UserProfile = Depends(require_guild_permission("user")),
    service: EventSignupService = Depends(get_event_signup_service),
):
    """List roles for an event with counts and the current user's selections."""
    ensure_guild_match(guild_id, current_user)
    data = await _guard(
        service.list_roles_with_state(
            guild_id,
            event_id,
            current_user.user_id,
            is_coordinator=is_coordinator(current_user),
        )
    )
    return _roles_response(data)


@router.post(
    "/{guild_id}/events/{event_id}/role-signup",
    response_model=EventRolesResponse,
    status_code=201,
)
async def sign_up_for_role(
    guild_id: int,
    event_id: int,
    payload: EventRoleSignupRequest,
    current_user: UserProfile = Depends(require_guild_permission("user")),
    service: EventSignupService = Depends(get_event_signup_service),
):
    """Sign the current user up for a specific role."""
    ensure_guild_match(guild_id, current_user)
    _enforce_signup_write_rate_limit(current_user.user_id)
    coordinator = is_coordinator(current_user)
    await _guard(
        service.sign_up_for_role(
            guild_id,
            event_id,
            payload.role_id,
            current_user.user_id,
            is_coordinator=coordinator,
        )
    )
    data = await _guard(
        service.list_roles_with_state(
            guild_id,
            event_id,
            current_user.user_id,
            is_coordinator=coordinator,
        )
    )
    return _roles_response(data)


@router.delete(
    "/{guild_id}/events/{event_id}/role-signup/{role_id}",
    response_model=EventRolesResponse,
)
async def withdraw_from_role(
    guild_id: int,
    event_id: int,
    role_id: int,
    current_user: UserProfile = Depends(require_guild_permission("user")),
    service: EventSignupService = Depends(get_event_signup_service),
):
    """Withdraw the current user from a specific role."""
    ensure_guild_match(guild_id, current_user)
    _enforce_signup_write_rate_limit(current_user.user_id)
    coordinator = is_coordinator(current_user)
    await _guard(
        service.withdraw_from_role(
            guild_id,
            event_id,
            role_id,
            current_user.user_id,
            is_coordinator=coordinator,
        )
    )
    data = await _guard(
        service.list_roles_with_state(
            guild_id,
            event_id,
            current_user.user_id,
            is_coordinator=coordinator,
        )
    )
    return _roles_response(data)


# ---------------------------------------------------------------------------
# Coordinator: roster, manual assignment, removal
# ---------------------------------------------------------------------------
@router.get(
    "/{guild_id}/events/{event_id}/roster",
    response_model=EventRosterResponse,
)
async def get_event_roster(
    guild_id: int,
    event_id: int,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Return the full coordinator roster (web signups + Discord RSVP count)."""
    ensure_guild_match(guild_id, current_user)
    data = await _guard(service.get_roster(guild_id, event_id, internal_api))
    return _roster_response(data)


@router.post(
    "/{guild_id}/events/{event_id}/roster/assign",
    response_model=EventRosterResponse,
)
async def assign_user_to_role(
    guild_id: int,
    event_id: int,
    user_id: str = Body(..., embed=True),
    role_id: int | None = Body(None, embed=True),
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Coordinator: assign a user to a role, or mark them interested (no role)."""
    ensure_guild_match(guild_id, current_user)
    if role_id is not None:
        await _guard(
            service.sign_up_for_role(
                guild_id,
                event_id,
                role_id,
                user_id,
                is_coordinator=True,
                acting_user_id=current_user.user_id,
            )
        )
    else:
        await _guard(
            service.mark_interest(guild_id, event_id, user_id, is_coordinator=True)
        )
    data = await _guard(service.get_roster(guild_id, event_id, internal_api))
    return _roster_response(data)


@router.delete(
    "/{guild_id}/events/{event_id}/roster/{user_id}",
    response_model=EventRosterResponse,
)
async def remove_user_from_event(
    guild_id: int,
    event_id: int,
    user_id: str,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Coordinator: fully remove a user from an event (interest + all roles)."""
    ensure_guild_match(guild_id, current_user)
    await _guard(service.remove_user_from_event(guild_id, event_id, user_id))
    data = await _guard(service.get_roster(guild_id, event_id, internal_api))
    return _roster_response(data)


# ---------------------------------------------------------------------------
# Coordinator: CSV export
# ---------------------------------------------------------------------------
@router.get("/{guild_id}/events/{event_id}/export")
async def export_event_signups(
    guild_id: int,
    event_id: int,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
):
    """Coordinator: export an event's web signups as CSV."""
    ensure_guild_match(guild_id, current_user)
    csv_text = await _guard(service.build_csv(guild_id, event_id))
    filename = f"event_{event_id}_signups.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Coordinator: channel messaging
# ---------------------------------------------------------------------------
@router.post(
    "/{guild_id}/events/{event_id}/message",
    response_model=EventMessageResponse,
)
async def send_event_message(
    guild_id: int,
    event_id: int,
    payload: EventMessageRequest,
    current_user: UserProfile = Depends(require_event_coordinator()),
    service: EventSignupService = Depends(get_event_signup_service),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Coordinator: send a message to a signup segment in a chosen channel.

    The bot validates it can send to the channel and posts the message with user
    mentions. Messages are never sent as DMs.
    """
    ensure_guild_match(guild_id, current_user)
    user_ids = await _guard(
        service.resolve_message_targets(
            guild_id, event_id, payload.target, payload.role_id
        )
    )
    try:
        channel_id = int(payload.channel_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid channel id") from exc

    try:
        result = await internal_api.send_channel_message(
            guild_id, channel_id, payload.message, user_ids
        )
    except Exception as exc:
        raise translate_internal_api_error(
            exc, "Failed to send message to the selected channel"
        ) from exc

    return EventMessageResponse(recipients=int(result.get("recipients", len(user_ids))))
