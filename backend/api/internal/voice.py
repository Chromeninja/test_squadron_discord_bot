"""Internal API routes for voice channels — DB-backed, API key protected.

These routes replace the voice-related portions of services/internal_api.py
for the DB layer. They do NOT proxy Discord gateway data.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.api_key import require_bot_api_key
from backend.db.repository.voice import VoiceRepository

router = APIRouter(prefix="/internal", tags=["internal-voice"])
logger = logging.getLogger(__name__)


def get_voice_repository() -> VoiceRepository:
    """Provide a VoiceRepository. Override in tests via dependency_overrides.

    The repository is stateless (it opens a connection per call via
    Database.get_connection()), so a fresh instance per request is cheap.
    """
    return VoiceRepository()


@router.get("/guilds/{guild_id}/voice/jtc")
async def list_jtc_channels(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return all active voice channels for a guild grouped by JTC parent."""
    channels = await repo.get_jtc_channels(guild_id)
    return {"channels": channels}


@router.get("/guilds/{guild_id}/voice/channels/{channel_id}")
async def get_voice_channel(
    guild_id: int,
    channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return a single voice channel by Discord voice_channel_id."""
    channel = await repo.get_voice_channel(guild_id, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Voice channel not found")
    return {"channel": channel}


@router.post("/guilds/{guild_id}/voice/channels")
async def create_voice_channel(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Create a new voice channel row.

    Required keys in payload: jtc_channel_id, owner_id, voice_channel_id.
    """
    try:
        channel = await repo.create_voice_channel(guild_id, payload)
    except KeyError as e:
        raise HTTPException(
            status_code=422, detail=f"missing required voice channel field: {e}"
        )
    return {"channel": channel}


@router.patch("/guilds/{guild_id}/voice/channels/{channel_id}")
async def update_voice_channel(
    guild_id: int,
    channel_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Update fields on a voice channel."""
    channel = await repo.update_voice_channel(guild_id, channel_id, payload)
    if channel is None:
        raise HTTPException(status_code=404, detail="Voice channel not found")
    return {"channel": channel}


@router.delete("/guilds/{guild_id}/voice/channels/{channel_id}")
async def delete_voice_channel(
    guild_id: int,
    channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Soft-delete a voice channel."""
    deleted = await repo.delete_voice_channel(guild_id, channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Voice channel not found")
    return {"success": True}
