from __future__ import annotations

"""
Dependency injection for FastAPI routes.

This module is the infrastructure entry point for the web backend.  It:

1. Resolves the project root and patches sys.path so that bot-level
   packages (services/, config/, etc.) are importable.
2. Owns the service-lifecycle singletons (ConfigService, VoiceService, ...)
   and exposes initialize_services / shutdown_services for the app lifespan.
3. Re-exports everything from the focused sub-modules so that existing
   from core.dependencies import X statements continue to work without
   modification.

For new code prefer importing directly from the focused modules:
  - core.internal_api_client -- InternalAPIClient, helpers
  - core.auth                -- session / user / guild-refresh deps
  - core.permissions         -- ROLE_HIERARCHY, require_* factories
"""

import logging
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Project Root Resolution (Observability-instrumented)
# ---------------------------------------------------------------------------
def project_root() -> Path:
    """
    Compute and return the project root directory.

    Resolution order:
    1. PROJECT_ROOT environment variable (dev/test only, if set and valid)
    2. Derived from this file location: web/backend/core/dependencies.py -> project root

    Returns:
        Path: Absolute path to project root directory.
    """
    # Derive from file location: web/backend/core/dependencies.py
    # parents[0] = core/, [1] = backend/, [2] = web/, [3] = project root
    derived = Path(__file__).resolve().parents[3]

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


# Compute once at module load -- must happen before any bot-package imports
_PROJECT_ROOT = project_root()
sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import ConfigLoader
from services.config_service import ConfigService
from services.db.database import Database
from services.ticket_form_service import TicketFormService
from services.ticket_service import TicketService
from services.voice_service import VoiceService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

_config_service: ConfigService | None = None
_config_loader: ConfigLoader | None = None
_voice_service: VoiceService | None = None
_ticket_service: TicketService | None = None
_ticket_form_service: TicketFormService | None = None


# ---------------------------------------------------------------------------
# Service getters
# ---------------------------------------------------------------------------


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


async def get_voice_service() -> VoiceService:
    """Lazily initialize and return a VoiceService instance for backend use.

    The backend does not operate a Discord bot; voice_service is constructed with
    bot=None and test_mode=True to avoid background tasks while still providing
    snapshot/query helpers.
    """
    global _voice_service

    if _voice_service is None:
        config_service = get_config_service()
        _voice_service = VoiceService(
            config_service=config_service, bot=None, test_mode=True
        )
        await _voice_service.initialize()

    return _voice_service


async def get_ticket_service() -> TicketService:
    """Lazily initialize and return a TicketService for backend use."""
    global _ticket_service
    if _ticket_service is None:
        _ticket_service = TicketService()
        _ticket_service._initialized = True
    return _ticket_service


async def get_ticket_form_service() -> TicketFormService:
    """Lazily initialize and return a TicketFormService for backend use."""
    global _ticket_form_service
    if _ticket_form_service is None:
        _ticket_form_service = TicketFormService()
        _ticket_form_service._initialized = True
    return _ticket_form_service


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


async def initialize_services() -> None:
    """Initialize services on application startup."""
    global _config_service, _config_loader

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

    db_path = config_dict.get("database", {}).get("path", "TESTDatabase.db")
    if not Path(db_path).is_absolute():
        db_path = str(_PROJECT_ROOT / db_path)

    await Database.initialize(db_path)

    _config_service = ConfigService(config_loader=_config_loader)
    await _config_service.initialize()

    logger.info(
        "Services initialized",
        extra={"db_path": db_path, "project_root": str(_PROJECT_ROOT)},
    )


async def shutdown_services() -> None:
    """Cleanup services on application shutdown."""
    from .internal_api_client import _internal_api_client as _api_client

    if _config_service:
        await _config_service.shutdown()

    if _voice_service:
        await _voice_service.shutdown()

    if _api_client:
        await _api_client.close()

    logger.info("Services shut down")


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------


async def get_db():
    """Dependency for database access."""
    async with Database.get_connection() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Backward-compatibility re-exports
# ---------------------------------------------------------------------------
# All symbols that existing routes import from this module are re-exported
# here so that from core.dependencies import X continues to work.
# New code should prefer importing from the focused sub-modules directly.

from .auth import (
    ROLE_VALIDATION_TTL,
    GuildValidationStatus,
    _ensure_fresh_guild_access,
    _now_ts,
    _refresh_authorized_guilds,
    _validate_guild_membership,
    get_current_user,
    get_user_authorized_guilds,
    require_any_guild_access,
    require_fresh_guild_access,
)
from .internal_api_client import (
    INTERNAL_API_TIMEOUT_SECONDS,
    InternalAPIClient,
    RecheckRequestBody,
    _extract_internal_api_detail,
    get_internal_api_client,
    translate_internal_api_error,
)
from .permissions import (
    ROLE_HIERARCHY,
    _has_minimum_role,
    require_bot_admin,
    require_bot_owner,
    require_discord_manager,
    require_event_coordinator,
    require_guild_permission,
    require_is_bot_owner,
    require_moderator,
    require_staff,
)

__all__ = [
    "INTERNAL_API_TIMEOUT_SECONDS",
    "ROLE_HIERARCHY",
    "ROLE_VALIDATION_TTL",
    "GuildValidationStatus",
    "InternalAPIClient",
    "RecheckRequestBody",
    "_ensure_fresh_guild_access",
    "_extract_internal_api_detail",
    "_has_minimum_role",
    "_now_ts",
    "_refresh_authorized_guilds",
    "_validate_guild_membership",
    "get_config_loader",
    "get_config_service",
    "get_current_user",
    "get_db",
    "get_internal_api_client",
    "get_ticket_form_service",
    "get_ticket_service",
    "get_user_authorized_guilds",
    "get_voice_service",
    "initialize_services",
    "project_root",
    "require_any_guild_access",
    "require_bot_admin",
    "require_bot_owner",
    "require_discord_manager",
    "require_event_coordinator",
    "require_fresh_guild_access",
    "require_guild_permission",
    "require_is_bot_owner",
    "require_moderator",
    "require_staff",
    "shutdown_services",
    "translate_internal_api_error",
]
