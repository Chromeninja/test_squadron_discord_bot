"""Internal API routes for guild config settings — DB-backed, API key protected.

These routes replace the config-related portions of services/internal_api.py
for the DB layer. They manage guild_settings via the ConfigRepository.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.api_key import require_bot_api_key
from backend.db.repository.config import ConfigRepository

router = APIRouter(prefix="/internal", tags=["internal-config"])
logger = logging.getLogger(__name__)


def get_config_repository() -> ConfigRepository:
    """Provide a ConfigRepository. Override in tests via dependency_overrides.

    The repository is stateless (it opens a connection per call via
    Database.get_connection()), so a fresh instance per request is cheap.
    """
    return ConfigRepository()


@router.get("/guilds/{guild_id}/config")
async def get_config(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Return all settings for a guild."""
    config = await repo.get_config(guild_id)
    return {"config": config}


@router.patch("/guilds/{guild_id}/config")
async def update_config(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Update multiple settings and return the updated config."""
    updated = await repo.update_config(guild_id, payload)
    return {"config": updated}


@router.get("/guilds/{guild_id}/config/settings/{key}")
async def get_setting(
    guild_id: int,
    key: str,
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Return a single setting value."""
    value = await repo.get_setting(guild_id, key)
    if value is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"key": key, "value": value}


@router.patch("/guilds/{guild_id}/config/settings/{key}")
async def set_setting(
    guild_id: int,
    key: str,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Set a single setting value."""
    setting_value = payload.get("value")
    await repo.set_setting(guild_id, key, setting_value)
    return {"key": key, "value": setting_value}


@router.post("/guilds/{guild_id}/config/refresh")
async def refresh_config(
    guild_id: int,
    payload: dict[str, Any] | None = None,
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Trigger a config refresh (no DB write; informational only).

    Optional "source" field in payload indicates the refresh trigger.
    """
    if payload is None:
        payload = {}
    return {
        "refreshed": True,
        "guild_id": guild_id,
        "source": payload.get("source"),
    }


@router.get("/guilds/{guild_id}/config/roles")
async def get_roles(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Return role configuration for a guild."""
    roles = await repo.get_guild_roles(guild_id)
    return {"roles": roles}


@router.get("/guilds/{guild_id}/config/channels")
async def get_channels(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Return channel configuration for a guild."""
    channels = await repo.get_guild_channels(guild_id)
    return {"channels": channels}


@router.get("/guilds/{guild_id}/config/jtc-channels")
async def get_jtc_channels(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: ConfigRepository = Depends(get_config_repository),
) -> dict[str, Any]:
    """Return join-to-create voice channels for a guild."""
    channels = await repo.get_jtc_channels(guild_id)
    return {"channels": channels}
