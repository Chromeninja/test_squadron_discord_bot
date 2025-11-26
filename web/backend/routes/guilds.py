"""Guild-specific management endpoints."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_admin_or_moderator,
    translate_internal_api_error,
)
from core.guild_settings import (
    get_bot_channel_settings,
    get_bot_role_settings,
    get_organization_settings,
    get_voice_selectable_roles,
    set_bot_channel_settings,
    set_bot_role_settings,
    set_organization_settings,
    set_voice_selectable_roles,
)
from core.schemas import (
    BotChannelSettings,
    BotRoleSettings,
    DiscordChannel,
    DiscordRole,
    GuildChannelsResponse,
    GuildMember,
    GuildMemberResponse,
    GuildMembersResponse,
    GuildRolesResponse,
    OrganizationSettings,
    OrganizationValidationRequest,
    OrganizationValidationResponse,
    UserProfile,
    VoiceSelectableRoles,
)
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/api/guilds", tags=["guilds"])


def _ensure_active_guild(current_user: UserProfile, guild_id: int) -> None:
    """Ensure the user has selected and is accessing their active guild."""
    if not current_user.active_guild_id:
        raise HTTPException(status_code=400, detail="No active guild selected")

    if str(guild_id) != str(current_user.active_guild_id):
        raise HTTPException(status_code=403, detail="Active guild mismatch")


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_role(role_data: dict) -> DiscordRole | None:
    role_id = _safe_int(role_data.get("id"))
    if role_id is None:
        return None

    name = role_data.get("name") or "Unnamed Role"
    color_value = role_data.get("color")
    color = _safe_int(color_value) if color_value is not None else None

    return DiscordRole(id=role_id, name=name, color=color)


def _coerce_member(member_data: dict) -> GuildMember | None:
    user_id = _safe_int(member_data.get("user_id"))
    if user_id is None:
        return None

    role_objs = []
    for role_data in member_data.get("roles", []):
        role = _coerce_role(role_data)
        if role:
            role_objs.append(role)

    return GuildMember(
        user_id=user_id,
        username=member_data.get("username"),
        discriminator=member_data.get("discriminator"),
        global_name=member_data.get("global_name"),
        avatar_url=member_data.get("avatar_url"),
        joined_at=member_data.get("joined_at"),
        created_at=member_data.get("created_at"),
        roles=role_objs,
    )


@router.get("/{guild_id}/roles/discord", response_model=GuildRolesResponse)
async def get_discord_roles(
    guild_id: int,
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Return roles for a guild sourced from the bot's internal API."""
    _ensure_active_guild(current_user, guild_id)
    try:
        roles_payload = await internal_api.get_guild_roles(guild_id)
    except Exception as exc:  # pragma: no cover - transport errors
        raise translate_internal_api_error(exc, "Failed to fetch roles") from exc

    roles: list[DiscordRole] = []
    for role in roles_payload:
        role_obj = _coerce_role(role)
        if role_obj:
            roles.append(role_obj)

    return GuildRolesResponse(roles=roles)


@router.get("/{guild_id}/channels/discord", response_model=GuildChannelsResponse)
async def get_discord_channels(
    guild_id: int,
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Return text channels for a guild sourced from the bot's internal API."""
    _ensure_active_guild(current_user, guild_id)
    try:
        channels_payload = await internal_api.get_guild_channels(guild_id)
    except Exception as exc:  # pragma: no cover - transport errors
        raise translate_internal_api_error(exc, "Failed to fetch channels") from exc

    channels: list[DiscordChannel] = []
    for channel in channels_payload:
        channel_id = channel.get("id")  # Already a string from bot API
        if channel_id:
            channels.append(
                DiscordChannel(
                    id=str(channel_id),  # Ensure it's a string
                    name=channel.get("name", "Unknown"),
                    category=channel.get("category"),
                    position=channel.get("position", 0),
                )
            )

    return GuildChannelsResponse(channels=channels)


@router.get("/{guild_id}/settings/bot-roles", response_model=BotRoleSettings)
async def get_bot_roles_settings(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Fetch stored bot role assignments for a guild."""
    _ensure_active_guild(current_user, guild_id)
    settings = await get_bot_role_settings(db, guild_id)
    return BotRoleSettings(**settings)


@router.put("/{guild_id}/settings/bot-roles", response_model=BotRoleSettings)
async def update_bot_roles_settings(
    guild_id: int,
    payload: BotRoleSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Persist admin, moderator, and member category role assignments for a guild."""
    _ensure_active_guild(current_user, guild_id)
    await set_bot_role_settings(
        db,
        guild_id,
        payload.bot_admins,
        payload.lead_moderators,
        payload.main_role,
        payload.affiliate_role,
        payload.nonmember_role,
    )
    updated = await get_bot_role_settings(db, guild_id)
    return BotRoleSettings(**updated)


@router.get("/{guild_id}/settings/bot-channels", response_model=BotChannelSettings)
async def get_bot_channels_settings(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Fetch stored bot channel assignments for a guild."""
    _ensure_active_guild(current_user, guild_id)
    settings = await get_bot_channel_settings(db, guild_id)
    return BotChannelSettings(**settings)


@router.put("/{guild_id}/settings/bot-channels", response_model=BotChannelSettings)
async def update_bot_channels_settings(
    guild_id: int,
    payload: BotChannelSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Persist bot channel assignments for a guild."""
    _ensure_active_guild(current_user, guild_id)
    await set_bot_channel_settings(
        db,
        guild_id,
        payload.verification_channel_id,
        payload.bot_spam_channel_id,
        payload.public_announcement_channel_id,
        payload.leadership_announcement_channel_id,
    )
    updated = await get_bot_channel_settings(db, guild_id)
    return BotChannelSettings(**updated)


@router.get(
    "/{guild_id}/settings/voice/selectable-roles",
    response_model=VoiceSelectableRoles,
)
async def get_voice_selectable_roles_settings(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Return selectable roles that voice automations can target for a guild."""
    _ensure_active_guild(current_user, guild_id)
    role_ids = await get_voice_selectable_roles(db, guild_id)
    return VoiceSelectableRoles(selectable_roles=role_ids)


@router.put(
    "/{guild_id}/settings/voice/selectable-roles",
    response_model=VoiceSelectableRoles,
)
async def update_voice_selectable_roles_settings(
    guild_id: int,
    payload: VoiceSelectableRoles,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Persist selectable voice role IDs for a guild."""
    _ensure_active_guild(current_user, guild_id)
    await set_voice_selectable_roles(db, guild_id, payload.selectable_roles)
    updated = await get_voice_selectable_roles(db, guild_id)
    return VoiceSelectableRoles(selectable_roles=updated)


@router.get(
    "/{guild_id}/members",
    response_model=GuildMembersResponse,
)
async def list_guild_members(
    guild_id: int,
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(100, ge=1, le=1000),
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Proxy paginated Discord member data from the bot's internal API."""
    _ensure_active_guild(current_user, guild_id)

    try:
        payload = await internal_api.get_guild_members(
            guild_id,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        raise translate_internal_api_error(
            exc,
            "Failed to fetch guild members",
        ) from exc

    members: list[GuildMember] = []
    for raw_member in payload.get("members", []):
        member_obj = _coerce_member(raw_member)
        if member_obj:
            members.append(member_obj)

    return GuildMembersResponse(
        members=members,
        page=payload.get("page", page),
        page_size=payload.get("page_size", page_size),
        total=payload.get("total", len(members)),
    )


@router.get(
    "/{guild_id}/members/{user_id}",
    response_model=GuildMemberResponse,
)
async def get_guild_member_detail(
    guild_id: int,
    user_id: int,
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Proxy a single Discord member lookup via the internal API."""
    _ensure_active_guild(current_user, guild_id)

    try:
        payload = await internal_api.get_guild_member(guild_id, user_id)
    except Exception as exc:
        raise translate_internal_api_error(
            exc,
            "Failed to fetch guild member",
        ) from exc

    member = _coerce_member(payload)
    if not member:
        raise HTTPException(
            status_code=502,
            detail="Invalid member payload from internal API",
        )

    return GuildMemberResponse(member=member)


# Organization Settings Endpoints

# Load RSI config
def _load_rsi_config() -> dict:
    """Load RSI configuration from config.yaml."""
    project_root = Path(__file__).parent.parent.parent.parent
    config_path = project_root / "config" / "config.yaml"
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            return config.get("rsi", {})
    except Exception:
        return {}


# Initialize RSI client (lazy)
_rsi_client = None


def _get_rsi_client():
    """Get or create RSI client singleton."""
    global _rsi_client
    if _rsi_client is None:
        from core.rsi_utils import RSIClient

        rsi_config = _load_rsi_config()
        requests_per_minute = rsi_config.get("requests_per_minute", 30)
        user_agent = rsi_config.get(
            "user_agent",
            "TEST-Squadron-Verification-Bot/1.0"
        )
        _rsi_client = RSIClient(
            requests_per_minute=requests_per_minute,
            user_agent=user_agent
        )
    return _rsi_client


@router.get(
    "/{guild_id}/settings/organization",
    response_model=OrganizationSettings
)
async def get_organization_settings_endpoint(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Fetch organization settings for a guild."""
    _ensure_active_guild(current_user, guild_id)
    settings = await get_organization_settings(db, guild_id)
    return OrganizationSettings(**settings)


@router.put(
    "/{guild_id}/settings/organization",
    response_model=OrganizationSettings
)
async def update_organization_settings_endpoint(
    guild_id: int,
    payload: OrganizationSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Update organization settings for a guild."""
    _ensure_active_guild(current_user, guild_id)
    await set_organization_settings(
        db,
        guild_id,
        payload.organization_sid,
        payload.organization_name,
    )
    updated = await get_organization_settings(db, guild_id)
    return OrganizationSettings(**updated)


@router.post(
    "/{guild_id}/organization/validate-sid",
    response_model=OrganizationValidationResponse
)
async def validate_organization_sid_endpoint(
    guild_id: int,
    payload: OrganizationValidationRequest,
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """Validate an organization SID by fetching from RSI."""
    _ensure_active_guild(current_user, guild_id)

    from core.rsi_utils import validate_organization_sid

    rsi_client = _get_rsi_client()

    is_valid, org_name, error_msg = await validate_organization_sid(
        payload.sid,
        rsi_client
    )

    return OrganizationValidationResponse(
        success=True,
        is_valid=is_valid,
        sid=payload.sid.strip().upper(),
        name=org_name,
        error=error_msg
    )
