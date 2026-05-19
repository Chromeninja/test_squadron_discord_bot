from __future__ import annotations

"""
Authentication and session management dependencies for FastAPI routes.

Provides ``get_current_user``, session refresh helpers, and guild-access
validation dependencies used by route handlers.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Literal

import httpx
from fastapi import Cookie, Depends, HTTPException, Request, Response

if TYPE_CHECKING:
    from collections.abc import Iterable

from .internal_api_client import InternalAPIClient, get_internal_api_client
from .request_id import get_request_id
from .schemas import GuildPermission, UserProfile
from .security import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    decode_session_token,
    set_session_cookie,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# TTL (seconds) for per-guild role re-validation against the Internal API.
ROLE_VALIDATION_TTL = int(os.getenv("ROLE_VALIDATION_TTL", "30"))

GuildValidationStatus = Literal["valid", "unavailable", "revoked"]


def _now_ts() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# Session / user extraction
# ---------------------------------------------------------------------------


async def get_current_user(
    session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> UserProfile:
    """
    Dependency to get the current authenticated user.

    Validates session cookie and returns user profile.
    Raises 401 if not authenticated.

    Args:
        session: Session token from cookie

    Returns:
        UserProfile of authenticated user

    Raises:
        HTTPException: 401 if not authenticated
    """
    if not session:
        logger.debug("get_current_user: session cookie missing")
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = await decode_session_token(session)
    if not user_data:
        logger.warning("get_current_user: invalid or expired session token")
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    if "authorized_guilds" in user_data:
        authorized_guilds_data = user_data["authorized_guilds"] or {}
        authorized_guilds: dict[str, GuildPermission] = {}
        for guild_id, perm_data in authorized_guilds_data.items():
            if isinstance(perm_data, GuildPermission):
                authorized_guilds[guild_id] = perm_data
            elif isinstance(perm_data, dict):
                authorized_guilds[guild_id] = GuildPermission(**perm_data)
            else:
                logger.warning(
                    "get_current_user: skipping invalid guild permission entry",
                    extra={"guild_id": guild_id, "type": type(perm_data).__name__},
                )
        user_data["authorized_guilds"] = authorized_guilds

    return UserProfile(**user_data)


def get_user_authorized_guilds(user: UserProfile) -> list[int]:
    """Get guild IDs where the user has elevated permissions."""
    guild_ids: list[int] = []
    for guild_id in user.authorized_guilds:
        try:
            guild_ids.append(int(guild_id))
        except (TypeError, ValueError):
            continue
    return guild_ids


# ---------------------------------------------------------------------------
# Live role validation
# ---------------------------------------------------------------------------


async def _validate_guild_membership(
    request: Request,
    current_user: UserProfile,
    internal_api: InternalAPIClient,
    guild_id_str: str,
) -> tuple[GuildValidationStatus, str | None]:
    """Fetch live member data for a guild and classify the validation result."""
    log_context = {
        "request_id": get_request_id(),
        "user_id": current_user.user_id,
        "guild_id": guild_id_str,
        "path": request.url.path,
    }

    try:
        guild_id_int = int(guild_id_str)
    except (TypeError, ValueError):
        logger.warning(
            "role validation failed - invalid guild id",
            extra={**log_context, "cause": "invalid_guild_id"},
        )
        return "revoked", None

    try:
        member = await internal_api.get_guild_member(
            guild_id_int,
            int(current_user.user_id),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.info(
                "user not found in guild - skipping role validation",
                extra={**log_context, "cause": "user_not_in_guild"},
            )
            return "revoked", None
        logger.warning(
            "role validation unavailable - internal API HTTP error",
            extra={
                **log_context,
                "cause": "internal_api_http_error",
                "status": exc.response.status_code,
            },
        )
        return "unavailable", None
    except Exception as exc:  # pragma: no cover - transport errors
        logger.warning(
            "role validation unavailable - internal API error",
            extra={**log_context, "cause": "internal_api_error", "error": str(exc)},
        )
        return "unavailable", None

    role_ids = member.get("role_ids") or [
        r.get("id") for r in (member.get("roles") or [])
    ]
    if not isinstance(role_ids, list):
        logger.warning(
            "role validation failed - invalid payload",
            extra={**log_context, "cause": "invalid_payload"},
        )
        return "unavailable", None

    def _to_int(value: object) -> int | None:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    from .guild_settings import fetch_bot_role_settings

    role_settings = await fetch_bot_role_settings(guild_id_int)

    user_roles_int = {rid for rid in (_to_int(r) for r in role_ids) if rid is not None}
    bot_admin_ids = {int(r) for r in role_settings.get("bot_admins", [])}
    discord_manager_ids = {int(r) for r in role_settings.get("discord_managers", [])}
    moderator_ids = {int(r) for r in role_settings.get("moderators", [])}
    event_coordinator_ids = {
        int(r) for r in role_settings.get("event_coordinators", [])
    }
    staff_ids = {int(r) for r in role_settings.get("staff", [])}

    computed_level: str | None = None
    if user_roles_int & bot_admin_ids:
        computed_level = "bot_admin"
    elif user_roles_int & discord_manager_ids:
        computed_level = "discord_manager"
    elif user_roles_int & moderator_ids:
        computed_level = "moderator"
    elif user_roles_int & event_coordinator_ids:
        computed_level = "event_coordinator"
    elif user_roles_int & staff_ids:
        computed_level = "staff"

    if not computed_level:
        logger.warning(
            "role validation failed - role mismatch",
            extra={**log_context, "cause": "role_mismatch"},
        )
        return "revoked", None

    logger.info(
        "role validation refreshed",
        extra={
            **log_context,
            "new_role": computed_level,
            "source": member.get("source"),
        },
    )
    return "valid", computed_level


async def _refresh_authorized_guilds(  # noqa: PLR0912, PLR0915
    request: Request,
    response: Response,
    raw_session: str | None,
    current_user: UserProfile,
    internal_api: InternalAPIClient,
    target_guilds: Iterable[str] | None = None,
    fail_on_missing: bool = False,
    force_refresh: bool = False,
) -> set[str]:
    """Refresh guild permissions for the provided guild IDs or all authorized guilds."""
    if not raw_session:
        raise HTTPException(
            status_code=401,
            detail={"code": "role_revoked", "message": "Session missing"},
        )

    user_data = await decode_session_token(raw_session)
    if not user_data:
        raise HTTPException(
            status_code=401,
            detail={"code": "role_revoked", "message": "Session invalid"},
        )

    authorized_map: dict[str, dict] = user_data.get("authorized_guilds") or {}
    roles_validated_at: dict[str, int] = user_data.get("roles_validated_at") or {}

    guild_ids = list(target_guilds) if target_guilds else list(authorized_map.keys())
    guild_ids = [gid for gid in guild_ids if gid in authorized_map]

    if target_guilds and not guild_ids:
        user_data["active_guild_id"] = None
        current_user.active_guild_id = None
        if fail_on_missing:
            clear_session_cookie(response)
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "role_revoked",
                    "message": "Your Discord permissions changed. Please sign in again.",
                },
            )

    removed: set[str] = set()
    session_mutated = False
    now_ts = _now_ts()

    for guild_id_str in guild_ids:
        last_ts = int(roles_validated_at.get(guild_id_str, 0) or 0)

        existing_perm = authorized_map.get(guild_id_str)
        if existing_perm is None:
            existing_source = ""
        elif isinstance(existing_perm, dict):
            existing_source = existing_perm.get("source", "") or ""
        elif hasattr(existing_perm, "source"):
            existing_source = getattr(existing_perm, "source", "") or ""
        else:
            existing_source = ""

        # Skip validation for Discord-native permissions
        if existing_source in ("bot_owner", "discord_owner", "discord_administrator"):
            if (
                force_refresh
                or not last_ts
                or (now_ts - last_ts) >= ROLE_VALIDATION_TTL
            ):
                roles_validated_at[guild_id_str] = now_ts
                session_mutated = True
            continue

        if not force_refresh and last_ts and (now_ts - last_ts) < ROLE_VALIDATION_TTL:
            continue

        validation_status, role_level = await _validate_guild_membership(
            request,
            current_user,
            internal_api,
            guild_id_str,
        )

        if validation_status == "unavailable":
            logger.info(
                "role validation unavailable - preserving existing guild access",
                extra={
                    "request_id": get_request_id(),
                    "user_id": current_user.user_id,
                    "guild_id": guild_id_str,
                    "path": request.url.path,
                },
            )
            continue

        if not role_level:
            removed.add(guild_id_str)
            roles_validated_at.pop(guild_id_str, None)
            session_mutated = True
            continue

        roles_validated_at[guild_id_str] = now_ts
        authorized_map[guild_id_str]["role_level"] = role_level
        if guild_id_str in current_user.authorized_guilds:
            current_user.authorized_guilds[guild_id_str].role_level = role_level
        session_mutated = True

    if removed:
        session_mutated = True
        for gid in removed:
            authorized_map.pop(gid, None)
            current_user.authorized_guilds.pop(gid, None)

        if user_data.get("active_guild_id") in removed:
            user_data["active_guild_id"] = None
            current_user.active_guild_id = None

    user_data["authorized_guilds"] = authorized_map
    user_data["roles_validated_at"] = roles_validated_at

    if session_mutated:
        await set_session_cookie(response, user_data)

    if fail_on_missing and removed & set(guild_ids):
        clear_session_cookie(response)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "role_revoked",
                "message": "Your Discord permissions changed. Please sign in again.",
            },
        )

    if not authorized_map:
        clear_session_cookie(response)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "role_revoked",
                "message": "You no longer have access to any guilds.",
            },
        )

    return removed


async def _ensure_fresh_guild_access(
    request: Request,
    response: Response,
    raw_session: str | None,
    current_user: UserProfile,
    internal_api: InternalAPIClient,
    force_refresh: bool = False,
) -> UserProfile:
    """Ensure the active guild's permissions are fresh, refreshing if needed."""
    from .pagination import is_all_guilds_mode

    if is_all_guilds_mode(current_user.active_guild_id):
        if not current_user.is_bot_owner:
            raise HTTPException(
                status_code=403,
                detail="All Guilds mode is only available to bot owners",
            )
        return current_user

    if not current_user.active_guild_id:
        raise HTTPException(status_code=400, detail="No active guild selected")

    await _refresh_authorized_guilds(
        request,
        response,
        raw_session,
        current_user,
        internal_api,
        target_guilds=[current_user.active_guild_id],
        fail_on_missing=True,
        force_refresh=force_refresh,
    )

    return current_user


# ---------------------------------------------------------------------------
# FastAPI dependency callables
# ---------------------------------------------------------------------------


async def require_fresh_guild_access(
    request: Request,
    response: Response,
    raw_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    current_user: UserProfile = Depends(get_current_user),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> UserProfile:
    """Dependency: verify active guild access is fresh (within TTL)."""
    await _ensure_fresh_guild_access(
        request,
        response,
        raw_session,
        current_user,
        internal_api,
        force_refresh=False,
    )
    return current_user


async def require_any_guild_access(
    request: Request,
    response: Response,
    raw_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    current_user: UserProfile = Depends(get_current_user),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> UserProfile:
    """
    Require user to have access to at least one guild.

    Used for endpoints that work across guilds (like /guilds list, /select-guild).
    Does NOT require active_guild_id to be set (used before guild selection).
    """
    force_refresh = request.query_params.get("force_refresh") in {"1", "true", "True"}

    await _refresh_authorized_guilds(
        request,
        response,
        raw_session,
        current_user,
        internal_api,
        force_refresh=force_refresh,
    )

    if not current_user.authorized_guilds:
        raise HTTPException(status_code=403, detail="No authorized guilds found")

    return current_user
