from __future__ import annotations

"""
Permission and authorization dependencies for FastAPI routes.

Provides role-hierarchy checking and ``require_*`` dependency factories
consumed by route handlers to enforce access control.
"""

import logging
from typing import TYPE_CHECKING

from fastapi import Cookie, Depends, HTTPException, Request, Response

from .auth import _ensure_fresh_guild_access, get_current_user
from .internal_api_client import InternalAPIClient, get_internal_api_client
from .security import SESSION_COOKIE_NAME

if TYPE_CHECKING:
    from .schemas import UserProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------

# Higher number = higher privilege.
ROLE_HIERARCHY: dict[str, int] = {
    "bot_owner": 7,
    "bot_admin": 6,
    "discord_manager": 5,
    "moderator": 4,
    "event_coordinator": 3,
    "staff": 2,
    "user": 1,
}


def _has_minimum_role(user_role: str, required_role: str) -> bool:
    """Check if user's role meets minimum requirement.

    Args:
        user_role: User's role level
        required_role: Minimum required role level

    Returns:
        True if user_role >= required_role in hierarchy
    """
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


# ---------------------------------------------------------------------------
# Permission dependency factory
# ---------------------------------------------------------------------------


def require_guild_permission(min_role: str):
    """Factory function to create permission dependency for specific role level.

    Checks user's permission level in their active guild against minimum
    requirement. Bot owners always pass regardless of guild membership.

    Args:
        min_role: Minimum required role level (bot_owner, bot_admin,
            discord_manager, moderator, event_coordinator, staff)

    Returns:
        Dependency function that validates permissions

    Example:
        @router.get("/admin-only", dependencies=[Depends(require_guild_permission("bot_admin"))])
    """

    async def check_permission(
        request: Request,
        response: Response,
        raw_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
        current_user: UserProfile = Depends(get_current_user),
        internal_api: InternalAPIClient = Depends(get_internal_api_client),
    ) -> UserProfile:
        """Check if user has required permission level in active guild."""
        from .pagination import is_all_guilds_mode

        await _ensure_fresh_guild_access(
            request,
            response,
            raw_session,
            current_user,
            internal_api,
        )

        if is_all_guilds_mode(current_user.active_guild_id):
            if not current_user.is_bot_owner:
                raise HTTPException(
                    status_code=403,
                    detail="All Guilds mode is only available to bot owners",
                )
            return current_user

        if not current_user.active_guild_id:
            raise HTTPException(status_code=400, detail="No active guild selected")

        guild_perm = current_user.authorized_guilds.get(current_user.active_guild_id)

        if not guild_perm:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized for guild {current_user.active_guild_id}",
            )

        if not _has_minimum_role(guild_perm.role_level, min_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {min_role} role (you have: {guild_perm.role_level})",
            )

        return current_user

    return check_permission


# ---------------------------------------------------------------------------
# Convenience dependency functions for common permission levels
# ---------------------------------------------------------------------------


def require_bot_admin():
    """Require bot_admin level or higher (bot_owner, bot_admin)."""
    return require_guild_permission("bot_admin")


def require_discord_manager():
    """Require discord_manager level or higher."""
    return require_guild_permission("discord_manager")


def require_moderator():
    """Require moderator level or higher."""
    return require_guild_permission("moderator")


def require_event_coordinator():
    """Require event_coordinator level or higher."""
    return require_guild_permission("event_coordinator")


def require_staff():
    """Require staff level or higher."""
    return require_guild_permission("staff")


def require_bot_owner():
    """Require bot_owner level only. Used for privileged operations like leaving guilds."""
    return require_guild_permission("bot_owner")


async def require_is_bot_owner(
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """
    Require user to be a bot owner (checked via session is_bot_owner flag).

    Does NOT require an active guild - useful for global operations like bot invite.
    """
    if not current_user.is_bot_owner:
        raise HTTPException(
            status_code=403,
            detail="This action requires bot owner permissions",
        )
    return current_user
