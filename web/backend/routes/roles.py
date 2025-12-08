"""Role delegation management endpoints.

These endpoints are deprecated and will be superseded by the guild bot role settings
(`delegation_policies` in `/api/guilds/{guild_id}/settings/bot-roles`). Keep for
backward compatibility until the dashboard migrates fully.
"""

from core.dependencies import get_db, require_discord_manager
from core.guild_settings import (
    get_role_delegation_policies,
    set_role_delegation_policies,
)
from core.schemas import (
    RoleDelegationConfig,
    RoleDelegationConfigResponse,
    RoleDelegationPolicy,
    UserProfile,
)
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["roles"])


@router.get(
    "/delegation",
    response_model=RoleDelegationConfigResponse,
)
async def get_role_delegation_config(
    current_user: UserProfile = Depends(require_discord_manager()),
    db=Depends(get_db),
):
    """Return delegation policies for the active guild."""
    if not current_user.active_guild_id:
        raise HTTPException(status_code=400, detail="Active guild not set")

    guild_id = int(current_user.active_guild_id)
    policies = await get_role_delegation_policies(db, guild_id)
    hydrated = [RoleDelegationPolicy(**policy) for policy in policies]
    return RoleDelegationConfigResponse(
        data=RoleDelegationConfig(policies=hydrated)
    )


@router.post(
    "/delegation",
    response_model=RoleDelegationConfigResponse,
)
async def upsert_role_delegation_config(
    payload: RoleDelegationConfig,
    current_user: UserProfile = Depends(require_discord_manager()),
    db=Depends(get_db),
):
    """Replace delegation policies for the active guild."""
    if not current_user.active_guild_id:
        raise HTTPException(status_code=400, detail="Active guild not set")

    guild_id = int(current_user.active_guild_id)
    normalized = await set_role_delegation_policies(
        db, guild_id, [policy.model_dump() for policy in payload.policies]
    )
    hydrated = [RoleDelegationPolicy(**policy) for policy in normalized]
    return RoleDelegationConfigResponse(
        data=RoleDelegationConfig(policies=hydrated)
    )
