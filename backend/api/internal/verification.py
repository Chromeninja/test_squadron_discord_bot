"""Internal API routes for verification — DB-backed, API key protected.

These routes provide CRUD and state-change operations on verification records
for the bot connector layer. All routes require X-Bot-Api-Key authentication.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.api_key import require_bot_api_key
from backend.db.repository.verification import VerificationRepository

router = APIRouter(prefix="/internal", tags=["internal-verification"])
logger = logging.getLogger(__name__)


def get_verification_repository() -> VerificationRepository:
    """Provide a VerificationRepository. Override in tests via dependency_overrides.

    The repository is stateless (it opens a connection per call via
    Database.get_connection()), so a fresh instance per request is cheap.
    """
    return VerificationRepository()


@router.get("/guilds/{guild_id}/verification")
async def list_all_verified(
    guild_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VerificationRepository = Depends(get_verification_repository),
) -> dict[str, Any]:
    """Return all verified members for a guild."""
    members = await repo.get_all_verified(guild_id)
    return {"members": members}


@router.get("/guilds/{guild_id}/verification/members/{user_id}")
async def get_verification_member(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VerificationRepository = Depends(get_verification_repository),
) -> dict[str, Any]:
    """Return a single member's verification record."""
    verification = await repo.get_verification(guild_id, user_id)
    if verification is None:
        raise HTTPException(status_code=404, detail="Verification record not found")
    return {"member": verification}


@router.post("/guilds/{guild_id}/verification/members/{user_id}")
async def create_verification_member(
    guild_id: int,
    user_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_bot_api_key),
    repo: VerificationRepository = Depends(get_verification_repository),
) -> dict[str, Any]:
    """Create or update a verification record."""
    payload["user_id"] = user_id
    created = await repo.create_verification(guild_id, payload)
    return {"member": created}


@router.post("/guilds/{guild_id}/verification/members/{user_id}/recheck")
async def queue_verification_recheck(
    guild_id: int,
    user_id: int,
    _: str = Depends(require_bot_api_key),
    repo: VerificationRepository = Depends(get_verification_repository),
) -> dict[str, Any]:
    """Queue a member's verification for re-check."""
    queued = await repo.set_needs_reverify(user_id, True)
    return {"queued": queued}
