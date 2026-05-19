"""Guild organization settings and validation endpoints."""

from __future__ import annotations

import logging

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_bot_admin,
    require_fresh_guild_access,
)
from core.guild_settings import (
    LogoValidationError,
    get_organization_settings,
    set_organization_settings,
    validate_logo_url,
)
from core.schemas import (
    LogoValidationRequest,
    LogoValidationResponse,
    OrganizationSettings,
    OrganizationSettingsResponse,
    OrganizationValidationRequest,
    OrganizationValidationResponse,
    UserProfile,
)
from core.validation import ensure_guild_match
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api/guilds", tags=["guilds"])
logger = logging.getLogger(__name__)


def _load_rsi_config() -> dict:
    """Return RSI configuration from the shared ConfigLoader cache."""
    from core.dependencies import get_config_loader

    loader = get_config_loader()
    config = loader.load_config()
    return config.get("rsi", {})


_rsi_client = None


def _get_rsi_client():
    """Get or create RSI client singleton."""
    global _rsi_client
    if _rsi_client is None:
        from core.rsi_utils import RSIClient

        rsi_config = _load_rsi_config()
        requests_per_minute = rsi_config.get("requests_per_minute", 30)
        user_agent = rsi_config.get("user_agent", "TEST-Squadron-Verification-Bot/1.0")
        _rsi_client = RSIClient(
            requests_per_minute=requests_per_minute,
            user_agent=user_agent,
        )
    return _rsi_client


async def _notify_refresh(
    internal_api: InternalAPIClient,
    guild_id: int,
    source: str | None = None,
) -> None:
    """Best-effort push refresh to the bot after config changes."""
    try:
        await internal_api.notify_guild_settings_refresh(guild_id, source=source)
    except Exception as exc:  # pragma: no cover - transport errors
        logger.warning(
            "Failed to notify bot about guild %s config change: %s", guild_id, exc
        )


@router.get(
    "/{guild_id}/settings/organization",
    response_model=OrganizationSettings,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_organization_settings_endpoint(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_bot_admin()),
) -> OrganizationSettings:
    """Fetch organization settings for a guild."""
    ensure_guild_match(guild_id, current_user)
    settings = await get_organization_settings(db, guild_id)
    return OrganizationSettings(**settings)


@router.put(
    "/{guild_id}/settings/organization",
    response_model=OrganizationSettingsResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def update_organization_settings_endpoint(
    guild_id: int,
    payload: OrganizationSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> OrganizationSettingsResponse:
    """Update organization settings for a guild."""
    ensure_guild_match(guild_id, current_user)

    validated_logo_url = None
    if payload.organization_logo_url:
        try:
            validated_logo_url = await validate_logo_url(payload.organization_logo_url)
        except LogoValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    current_org = await get_organization_settings(db, guild_id)
    logo_changed = current_org.get("organization_logo_url") != validated_logo_url

    await set_organization_settings(
        db,
        guild_id,
        payload.organization_sid,
        payload.organization_name,
        validated_logo_url,
    )
    updated = await get_organization_settings(db, guild_id)
    await _notify_refresh(internal_api, guild_id, source="organization")

    verification_message_updated: bool | None = None
    if logo_changed:
        try:
            await internal_api.resend_verification_message(guild_id)
            verification_message_updated = True
        except Exception as exc:
            logger.warning(
                "Failed to resend verification message for guild %s after logo update: %s",
                guild_id,
                exc,
            )
            verification_message_updated = False

    return OrganizationSettingsResponse(
        **updated,
        verification_message_updated=verification_message_updated,
    )


@router.post(
    "/{guild_id}/organization/validate-sid",
    response_model=OrganizationValidationResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def validate_organization_sid_endpoint(
    guild_id: int,
    payload: OrganizationValidationRequest,
    current_user: UserProfile = Depends(require_bot_admin()),
) -> OrganizationValidationResponse:
    """Validate an organization SID by fetching from RSI."""
    ensure_guild_match(guild_id, current_user)

    from core.rsi_utils import validate_organization_sid

    rsi_client = _get_rsi_client()
    is_valid, org_name, error_msg = await validate_organization_sid(
        payload.sid,
        rsi_client,
    )

    return OrganizationValidationResponse(
        success=True,
        is_valid=is_valid,
        sid=payload.sid.strip().upper(),
        organization_name=org_name,
        error=error_msg,
    )


@router.post(
    "/{guild_id}/organization/validate-logo",
    response_model=LogoValidationResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def validate_logo_url_endpoint(
    guild_id: int,
    payload: LogoValidationRequest,
    current_user: UserProfile = Depends(require_bot_admin()),
) -> LogoValidationResponse:
    """Validate a logo URL is reachable and returns an acceptable image."""
    ensure_guild_match(guild_id, current_user)

    try:
        validated_url = await validate_logo_url(payload.url)
        return LogoValidationResponse(
            success=True,
            is_valid=True,
            url=validated_url,
            error=None,
        )
    except LogoValidationError as exc:
        return LogoValidationResponse(
            success=True,
            is_valid=False,
            url=None,
            error=str(exc),
        )
