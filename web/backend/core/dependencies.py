from __future__ import annotations

"""
Dependency injection for FastAPI routes.

Provides access to configuration, database, and session management.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import Cookie, Depends, HTTPException, Request, Response

if TYPE_CHECKING:
    from collections.abc import Iterable


# ---------------------------------------------------------------------------
# Project Root Resolution (Observability-instrumented)
# ---------------------------------------------------------------------------
def project_root() -> Path:
    """
    Compute and return the project root directory.

    Resolution order:
    1. PROJECT_ROOT environment variable (dev/test only, if set and valid)
    2. Derived from this file's location: web/backend/core/dependencies.py -> project root

    Returns:
        Path: Absolute path to project root directory.

    Observability:
        - Logs INFO on first resolution with resolved path
        - Logs INFO if PROJECT_ROOT env override is used
        - Logs WARNING if PROJECT_ROOT env points to non-existent directory
    """
    # Derive from file location: web/backend/core/dependencies.py
    # parents[0] = core/, [1] = backend/, [2] = web/, [3] = project root
    derived = Path(__file__).resolve().parents[3]

    # Allow override only in non-production environments to avoid sys.path injection risks
    env = os.environ.get("ENV", "").lower()
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root and env in {"dev", "test"}:
        env_path = Path(env_root).resolve()
        if env_path.is_dir():
            logging.getLogger(__name__).info(
                "Project root overridden via PROJECT_ROOT env",
                extra={"project_root": str(env_path)},
            )
            return env_path
        logging.getLogger(__name__).warning(
            "PROJECT_ROOT env points to non-existent directory; falling back to derived path",
            extra={"invalid_path": str(env_path)},
        )

    return derived


# Compute once at module load for sys.path setup
_PROJECT_ROOT = project_root()
sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import ConfigLoader
from services.config_service import ConfigService
from services.db.database import Database
from services.voice_service import VoiceService

from .request_id import get_request_id
from .schemas import UserProfile
from .security import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    decode_session_token,
    set_session_cookie,
)

logger = logging.getLogger(__name__)

# Global service instances
_config_service: ConfigService | None = None
_config_loader: ConfigLoader | None = None

# Internal API client singleton
_internal_api_client: InternalAPIClient | None = None
_voice_service: VoiceService | None = None


def get_internal_api_client() -> InternalAPIClient:
    """Return the cached InternalAPIClient instance."""
    global _internal_api_client
    if _internal_api_client is None:
        _internal_api_client = InternalAPIClient()
    return _internal_api_client


async def get_voice_service() -> VoiceService:
    """Lazily initialize and return a VoiceService instance for backend use.

    The backend does not operate a Discord bot; voice_service is constructed with
    bot=None and test_mode=True to avoid background tasks while still providing
    snapshot/query helpers.
    """

    global _voice_service

    if _voice_service is None:
        config_service = get_config_service()
        _voice_service = VoiceService(config_service=config_service, bot=None, test_mode=True)
        await _voice_service.initialize()

    return _voice_service


async def initialize_services():
    """Initialize services on application startup.

    Observability:
        - Logs INFO with resolved config path on successful load
        - Logs WARNING if config file is missing (degraded mode)
        - Logs ERROR if config YAML is invalid
        - Logs INFO with database path on successful initialization
    """
    global _config_service, _config_loader

    # Load global config once via centralized loader (supports CONFIG_PATH override)
    _config_loader = ConfigLoader()
    config_dict = _config_loader.load_config()

    config_status = _config_loader.get_config_status()
    logger.info(
        "Config load status",
        extra={
            "config_path": config_status.get("config_path"),
            "config_status": config_status.get("config_status"),
        },
    )

    # Initialize database with configured path
    db_path = config_dict.get("database", {}).get("path", "TESTDatabase.db")
    # Make db_path absolute if relative
    if not Path(db_path).is_absolute():
        db_path = str(_PROJECT_ROOT / db_path)

    await Database.initialize(db_path)

    # Initialize config service
    _config_service = ConfigService(config_loader=_config_loader)
    await _config_service.initialize()

    logger.info(
        "Services initialized",
        extra={"db_path": db_path, "project_root": str(_PROJECT_ROOT)},
    )


async def shutdown_services():
    """Cleanup services on application shutdown."""
    if _config_service:
        await _config_service.shutdown()

    if _voice_service:
        await _voice_service.shutdown()

    # Close internal API client
    if _internal_api_client:
        await _internal_api_client.close()

    logger.info("Services shut down")


def get_config_service() -> ConfigService:
    """Get the global ConfigService instance."""
    if _config_service is None:
        raise RuntimeError("ConfigService not initialized")
    return _config_service


def get_config_loader() -> ConfigLoader:
    """Get the global ConfigLoader instance."""
    if _config_loader is None:
        raise RuntimeError("ConfigLoader not initialized")
    return _config_loader


async def get_db():
    """
    Dependency for database access.

    Yields a connection context manager from the Database class.
    """
    async with Database.get_connection() as conn:
        yield conn


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

    user_data = decode_session_token(session)
    if not user_data:
        logger.warning("get_current_user: invalid or expired session token")
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Reconstruct GuildPermission objects from dict
    from .schemas import GuildPermission

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


# Role hierarchy for permission checking
# Higher number = higher privilege
ROLE_HIERARCHY = {
    "bot_owner": 6,
    "bot_admin": 5,
    "discord_manager": 4,
    "moderator": 3,
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


def require_guild_permission(min_role: str):
    """Factory function to create permission dependency for specific role level.

    Checks user's permission level in their active guild against minimum requirement.
    Bot owners always pass regardless of guild membership.

    Args:
        min_role: Minimum required role level (bot_owner, bot_admin, discord_manager, moderator, staff)

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

        # Bot owners in "All Guilds" mode have implicit bot_owner permission
        if is_all_guilds_mode(current_user.active_guild_id):
            if not current_user.is_bot_owner:
                raise HTTPException(
                    status_code=403,
                    detail="All Guilds mode is only available to bot owners",
                )
            # Bot owners always pass any permission check
            return current_user

        # User must have selected a guild
        if not current_user.active_guild_id:
            raise HTTPException(status_code=400, detail="No active guild selected")

        # Get user's permission for active guild
        guild_perm = current_user.authorized_guilds.get(current_user.active_guild_id)

        if not guild_perm:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized for guild {current_user.active_guild_id}",
            )

        # Check if user's role meets minimum requirement
        if not _has_minimum_role(guild_perm.role_level, min_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {min_role} role (you have: {guild_perm.role_level})",
            )

        return current_user

    return check_permission


# Convenience dependency functions for common permission levels
def require_bot_admin():
    """Require bot_admin level or higher (bot_owner, bot_admin)."""
    return require_guild_permission("bot_admin")


def require_discord_manager():
    """Require discord_manager level or higher (bot_owner, bot_admin, discord_manager)."""
    return require_guild_permission("discord_manager")


def require_moderator():
    """Require moderator level or higher (bot_owner, bot_admin, discord_manager, moderator)."""
    return require_guild_permission("moderator")


def require_staff():
    """Require staff level or higher (bot_owner, bot_admin, discord_manager, moderator, staff)."""
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


# Fresh role validation (TTL-based) against Internal API
ROLE_VALIDATION_TTL = int(os.getenv("ROLE_VALIDATION_TTL", "30"))


def _now_ts() -> int:
    return int(time.time())


async def _validate_guild_membership(
    request: Request,
    current_user: UserProfile,
    internal_api: InternalAPIClient,
    guild_id_str: str,
) -> str | None:
    """Fetch live member data for a guild and return the computed role level."""
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
        return None

    try:
        member = await internal_api.get_guild_member(
            guild_id_int,
            int(current_user.user_id),
        )
    except httpx.HTTPStatusError as exc:
        # 404 means user is not in the guild - this is expected if they left
        # Don't fail validation, just return None to preserve existing permission
        if exc.response.status_code == 404:
            logger.info(
                "user not found in guild - skipping role validation",
                extra={**log_context, "cause": "user_not_in_guild"},
            )
            return None
        # Other HTTP errors
        logger.warning(
            "role validation failed - internal API HTTP error",
            extra={
                **log_context,
                "cause": "internal_api_http_error",
                "status": exc.response.status_code,
            },
        )
        return None
    except Exception as exc:  # pragma: no cover - transport errors
        logger.warning(
            "role validation failed - internal API error",
            extra={**log_context, "cause": "internal_api_error", "error": str(exc)},
        )
        return None

    role_ids = member.get("role_ids") or [
        r.get("id") for r in (member.get("roles") or [])
    ]
    if not isinstance(role_ids, list):
        logger.warning(
            "role validation failed - invalid payload",
            extra={**log_context, "cause": "invalid_payload"},
        )
        return None

    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    from .guild_settings import fetch_bot_role_settings

    role_settings = await fetch_bot_role_settings(guild_id_int)

    user_roles_int = {rid for rid in (_to_int(r) for r in role_ids) if rid is not None}
    bot_admin_ids = {int(r) for r in role_settings.get("bot_admins", [])}
    discord_manager_ids = {int(r) for r in role_settings.get("discord_managers", [])}
    moderator_ids = {int(r) for r in role_settings.get("moderators", [])}
    staff_ids = {int(r) for r in role_settings.get("staff", [])}

    computed_level = None
    if user_roles_int & bot_admin_ids:
        computed_level = "bot_admin"
    elif user_roles_int & discord_manager_ids:
        computed_level = "discord_manager"
    elif user_roles_int & moderator_ids:
        computed_level = "moderator"
    elif user_roles_int & staff_ids:
        computed_level = "staff"

    if not computed_level:
        logger.warning(
            "role validation failed - role mismatch",
            extra={**log_context, "cause": "role_mismatch"},
        )
        return None

    logger.info(
        "role validation refreshed",
        extra={
            **log_context,
            "new_role": computed_level,
            "source": member.get("source"),
        },
    )
    return computed_level


async def _refresh_authorized_guilds(  # noqa: PLR0912, PLR0915 - centralizes session refresh flow
    request: Request,
    response: Response,
    raw_session: str | None,
    current_user: UserProfile,
    internal_api: InternalAPIClient,
    target_guilds: Iterable[str] | None = None,
    fail_on_missing: bool = False,
    force_refresh: bool = False,
):
    """Refresh guild permissions for the provided guild IDs or all authorized guilds."""
    if not raw_session:
        raise HTTPException(
            status_code=401,
            detail={"code": "role_revoked", "message": "Session missing"},
        )

    user_data = decode_session_token(raw_session)
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

        # Check if this guild has Discord-native permissions that don't need role validation
        existing_perm = authorized_map.get(guild_id_str)
        # Handle both dict (from raw session) and GuildPermission (from get_current_user)
        if existing_perm is None:
            existing_source = ""
        elif isinstance(existing_perm, dict):
            existing_source = existing_perm.get("source", "") or ""
        elif hasattr(existing_perm, "source"):
            existing_source = getattr(existing_perm, "source", "") or ""
        else:
            existing_source = ""

        # Skip validation for Discord-native permissions (bot_owner, discord_owner, discord_administrator)
        if existing_source in ("bot_owner", "discord_owner", "discord_administrator"):
            # Just update the timestamp to show we checked
            if (
                force_refresh
                or not last_ts
                or (now_ts - last_ts) >= ROLE_VALIDATION_TTL
            ):
                roles_validated_at[guild_id_str] = now_ts
                session_mutated = True
            continue

        # Only validate role-based permissions within TTL
        if not force_refresh and last_ts and (now_ts - last_ts) < ROLE_VALIDATION_TTL:
            continue

        role_level = await _validate_guild_membership(
            request,
            current_user,
            internal_api,
            guild_id_str,
        )

        if not role_level:
            # Role validation failed - remove this guild
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
        set_session_cookie(response, user_data)

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
):
    from .pagination import is_all_guilds_mode

    # Bot owners in "All Guilds" mode bypass per-guild validation
    if is_all_guilds_mode(current_user.active_guild_id):
        if not current_user.is_bot_owner:
            raise HTTPException(
                status_code=403,
                detail="All Guilds mode is only available to bot owners",
            )
        # Skip guild-specific validation for cross-guild mode
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


async def require_fresh_guild_access(
    request: Request,
    response: Response,
    raw_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    current_user: UserProfile = Depends(get_current_user),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    await _ensure_fresh_guild_access(
        request,
        response,
        raw_session,
        current_user,
        internal_api,
        force_refresh=False,
    )
    return current_user


# Special dependency for guild selection endpoints (before guild is selected)
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


# Internal API client for proxying requests to bot's internal server


def _extract_internal_api_detail(response: httpx.Response) -> str | None:
    """Try to pull a useful error message out of an internal API response."""
    if response is None:
        return None

    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or None

    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, dict):
                nested = value.get("message")
                if nested:
                    return nested
            elif value:
                return str(value)
    elif isinstance(payload, str) and payload:
        return payload

    return None


def translate_internal_api_error(exc: Exception, default_detail: str) -> HTTPException:
    """Convert httpx exceptions into FastAPI-friendly HTTPException objects."""
    if isinstance(exc, httpx.HTTPStatusError):
        detail = _extract_internal_api_detail(exc.response) or default_detail
        return HTTPException(status_code=exc.response.status_code, detail=detail)

    if isinstance(exc, httpx.RequestError):
        return HTTPException(status_code=503, detail=f"{default_detail}: {exc!s}")

    return HTTPException(status_code=500, detail=f"{default_detail}: {exc!s}")


class InternalAPIClient:
    """
    HTTP client for calling the bot's internal API.

    Handles authentication and provides typed methods for internal endpoints.
    """

    def __init__(self):
        self.base_url = os.getenv("INTERNAL_API_URL", "http://127.0.0.1:8082")
        self.api_key = os.getenv("INTERNAL_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

        # Avoid leaking any secret-related info to logs
        import logging

        logger = logging.getLogger(__name__)
        if self.api_key:
            logger.debug("InternalAPIClient initialized with authentication enabled")
        else:
            logger.warning(
                "InternalAPIClient initialized without INTERNAL_API_KEY; internal API calls may be unauthorized"
            )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url, headers=headers, timeout=10.0
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_bot_owner_ids(self) -> list[int]:
        """
        Fetch bot owner IDs from internal API.

        Supports single owner, team owners, and environment overrides.

        Returns:
            list of Discord user IDs who are bot owners

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.get("/bot-owner-ids")
        response.raise_for_status()
        payload = response.json()
        return payload.get("owner_ids", [])

    async def get_health_report(self):
        """Get comprehensive health report from internal API."""
        client = await self._get_client()
        response = await client.get("/health/report")
        response.raise_for_status()
        return response.json()

    async def get_last_errors(self, limit: int = 1):
        """Get most recent error log entries."""
        client = await self._get_client()
        response = await client.get("/errors/last", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def export_logs(self, max_bytes: int = 1048576):
        """Export bot logs as downloadable content."""
        client = await self._get_client()
        response = await client.get("/logs/export", params={"max_bytes": max_bytes})
        response.raise_for_status()
        return response.content

    async def get_guilds(self) -> list[dict]:
        """Fetch guilds where the bot is currently installed."""
        client = await self._get_client()
        response = await client.get("/guilds")
        response.raise_for_status()
        payload = response.json()
        return payload.get("guilds", [])

    async def get_guild_channels(self, guild_id: int) -> list[dict]:
        """Fetch text channels for a guild from internal API."""
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/channels")
        response.raise_for_status()
        payload = response.json()
        return payload.get("channels", [])

    async def get_guild_roles(self, guild_id: int) -> list[dict]:
        """Fetch Discord roles for a guild."""
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/roles")
        response.raise_for_status()
        payload = response.json()
        return payload.get("roles", [])

    async def get_guild_stats(self, guild_id: int) -> dict:
        """
        Fetch basic statistics for a guild (member count, etc).

        Returns:
            dict with keys: guild_id, member_count, approximate_member_count
        """
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/stats")
        response.raise_for_status()
        return response.json()

    async def get_guild_members(
        self, guild_id: int, page: int = 1, page_size: int = 100
    ) -> dict:
        """
        Fetch paginated list of guild members with Discord enrichment.

        Args:
            guild_id: Discord guild ID
            page: Page number (1-indexed)
            page_size: Items per page (max 1000)

        Returns:
            dict with keys: members (list), page, page_size, total
        """
        client = await self._get_client()
        response = await client.get(
            f"/guilds/{guild_id}/members", params={"page": page, "page_size": page_size}
        )
        response.raise_for_status()
        return response.json()

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict:
        """
        Fetch single guild member with Discord enrichment.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            dict with member data
        """
        client = await self._get_client()
        response = await client.get(f"/guilds/{guild_id}/members/{user_id}")
        response.raise_for_status()
        return response.json()

    async def recheck_user(
        self, guild_id: int, user_id: int, admin_user_id: str | None = None, log_leadership: bool = True
    ) -> dict:
        """
        Trigger reverification check for a specific user.

        Calls the bot's internal recheck endpoint to re-validate
        the user's RSI organization membership and update roles.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            admin_user_id: Optional Discord user ID of admin triggering recheck
            log_leadership: Whether to post individual leadership log message (default True)

        Returns:
            dict with recheck results (message, roles_updated, status, diff, etc.)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        json_body = {"log_leadership": log_leadership}
        if admin_user_id:
            json_body["admin_user_id"] = admin_user_id

        response = await client.post(
            f"/guilds/{guild_id}/members/{user_id}/recheck",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def notify_guild_settings_refresh(
        self, guild_id: int, source: str | None = None
    ) -> dict:
        """Notify the bot that guild configuration has changed."""
        client = await self._get_client()
        json_body = {"source": source} if source else None
        response = await client.post(
            f"/guilds/{guild_id}/config/refresh",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def resend_verification_message(self, guild_id: int) -> dict:
        """Trigger the bot to resend the verification message for a guild."""
        client = await self._get_client()
        response = await client.post(f"/guilds/{guild_id}/verification/resend")
        response.raise_for_status()
        return response.json()

    async def get_voice_channel_members(self, voice_channel_id: int) -> list[int]:
        """
        Get member IDs currently in a voice channel via bot's gateway cache.

        Args:
            voice_channel_id: Discord voice channel ID

        Returns:
            list of member IDs in the channel

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.get(f"/voice/members/{voice_channel_id}")
        response.raise_for_status()
        payload = response.json()
        return payload.get("member_ids", [])

    async def post_bulk_recheck_summary(
        self,
        guild_id: int,
        admin_user_id: int,
        scope_label: str,
        status_rows: list[dict],
        csv_bytes: str,
        csv_filename: str,
    ) -> dict:
        """
        Post bulk recheck summary to leadership channel.

        Args:
            guild_id: Discord guild ID
            admin_user_id: Discord user ID of admin who triggered recheck
            scope_label: Description of recheck scope (e.g., "web bulk recheck")
            status_rows: List of StatusRow data as dicts
            csv_bytes: Base64-encoded CSV file content
            csv_filename: Name for the CSV file

        Returns:
            dict with keys: success, channel_name

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        json_body = {
            "admin_user_id": admin_user_id,
            "scope_label": scope_label,
            "status_rows": status_rows,
            "csv_bytes": csv_bytes,
            "csv_filename": csv_filename,
        }
        response = await client.post(
            f"/guilds/{guild_id}/bulk-recheck/summary",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def leave_guild(self, guild_id: int) -> dict:
        """
        Make the bot leave a guild.

        This is a privileged operation - caller must validate bot owner permissions.

        Args:
            guild_id: Discord guild ID to leave

        Returns:
            dict with keys: success, guild_id, guild_name

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        client = await self._get_client()
        response = await client.post(f"/guilds/{guild_id}/leave")
        response.raise_for_status()
        return response.json()
