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


# ── Cooldown ────────────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/voice/cooldown/{jtc_channel_id}/{user_id}")
async def check_cooldown(
    guild_id: int,
    jtc_channel_id: int,
    user_id: int,
    cooldown_seconds: int = 5,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return whether the user is on cooldown for channel creation."""
    on_cooldown = await repo.check_cooldown(
        guild_id, jtc_channel_id, user_id, cooldown_seconds
    )
    return {"on_cooldown": on_cooldown}


@router.post("/guilds/{guild_id}/voice/cooldown/{jtc_channel_id}/{user_id}")
async def update_cooldown(
    guild_id: int,
    jtc_channel_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Reset the cooldown timestamp for a user to now."""
    await repo.update_cooldown(guild_id, jtc_channel_id, user_id)
    return {"success": True}


# ── Ownership queries ────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/voice/channels/user/{user_id}/jtc/{jtc_channel_id}")
async def get_user_channel_in_jtc(
    guild_id: int,
    user_id: int,
    jtc_channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return the voice_channel_id owned by user_id under a specific JTC, or null."""
    channel_id = await repo.get_user_channel_in_jtc(guild_id, jtc_channel_id, user_id)
    return {"voice_channel_id": channel_id}


@router.get("/guilds/{guild_id}/voice/channels/user/{user_id}")
async def get_any_user_channel(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return any active voice_channel_id owned by user_id in the guild, or null."""
    channel_id = await repo.get_any_user_channel(guild_id, user_id)
    return {"voice_channel_id": channel_id}


@router.get("/guilds/{guild_id}/voice/channels/user/{user_id}/info")
async def get_user_channel_info(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return the full channel row for a user's active channel, or 404."""
    info = await repo.get_user_channel_info(guild_id, user_id)
    if info is None:
        raise HTTPException(status_code=404, detail="No active channel found for user")
    return {"channel": info}


@router.get("/guilds/{guild_id}/voice/channels/owned/{voice_channel_id}/jtc")
async def get_jtc_for_owned_channel(
    guild_id: int,
    voice_channel_id: int,
    owner_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return the JTC channel ID for a channel owned by owner_id, or null."""
    jtc_id = await repo.get_jtc_for_owned_channel(guild_id, voice_channel_id, owner_id)
    return {"jtc_channel_id": jtc_id}


@router.get("/guilds/{guild_id}/voice/channels/active")
async def get_all_active_channels(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return all active voice channels (owner_id, voice_channel_id, created_at)."""
    channels = await repo.get_all_active_channels(guild_id)
    return {"channels": channels}


@router.get("/guilds/{guild_id}/voice/channels/active/ids")
async def get_active_channel_ids(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Return a flat list of active voice_channel_id values for the guild."""
    ids = await repo.get_active_channel_ids(guild_id)
    return {"channel_ids": ids}


# ── Cleanup / purge ──────────────────────────────────────────────────────────


@router.delete("/guilds/{guild_id}/voice/channels/{channel_id}/records")
async def cleanup_channel_records(
    guild_id: int,
    channel_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Hard-delete all DB records for a voice channel (settings + channel row)."""
    await repo.cleanup_channel_records(guild_id, channel_id)
    return {"success": True}


@router.delete("/guilds/{guild_id}/voice/purge")
async def purge_voice_data(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Purge all voice data for a guild, or a single user if user_id is provided."""
    user_id: int | None = payload.get("user_id")
    deleted = await repo.purge_voice_data(guild_id, user_id)
    return {"deleted": deleted}


@router.delete("/guilds/{guild_id}/voice/jtc/purge")
async def purge_stale_jtc_data(
    guild_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: VoiceRepository = Depends(get_voice_repository),
) -> dict[str, Any]:
    """Purge voice data for stale JTC channel IDs.

    payload must contain: stale_jtc_ids (list[int])
    """
    raw = payload.get("stale_jtc_ids", [])
    stale: set[int] = {int(v) for v in raw}
    deleted = await repo.purge_stale_jtc_data(guild_id, stale)
    return {"deleted": deleted}
