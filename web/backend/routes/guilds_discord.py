"""Guild Discord data proxy endpoints (roles, channels, members)."""

from __future__ import annotations

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_fresh_guild_access,
    require_staff,
    translate_internal_api_error,
)
from core.schemas import (
    DiscordChannel,
    DiscordRole,
    GuildChannelsResponse,
    GuildMember,
    GuildMemberResponse,
    GuildMembersResponse,
    GuildRolesResponse,
    UserProfile,
)
from core.validation import ensure_guild_match, safe_int
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/api/guilds", tags=["guilds"])


def _coerce_role(role_data: dict) -> DiscordRole | None:
    role_id = role_data.get("id")
    if role_id is None:
        return None

    role_id_str = str(role_id)
    name = role_data.get("name") or "Unnamed Role"
    color_value = role_data.get("color")
    color = safe_int(color_value) if color_value is not None else None

    return DiscordRole(
        id=role_id_str,
        name=str(name),
        color=color,
    )


def _coerce_member(member_data: dict) -> GuildMember | None:
    user_id = member_data.get("user_id")
    user_id_int = safe_int(user_id)
    if user_id_int is None:
        return None

    roles: list[DiscordRole] = []
    for role in member_data.get("roles", []):
        if not isinstance(role, dict):
            continue
        role_obj = _coerce_role(role)
        if role_obj:
            roles.append(role_obj)

    return GuildMember(
        user_id=user_id_int,
        username=member_data.get("username"),
        discriminator=member_data.get("discriminator"),
        global_name=member_data.get("global_name"),
        avatar_url=member_data.get("avatar_url"),
        joined_at=member_data.get("joined_at"),
        created_at=member_data.get("created_at"),
        roles=roles,
    )


@router.get(
    "/{guild_id}/roles/discord",
    response_model=GuildRolesResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_discord_roles(
    guild_id: int,
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> GuildRolesResponse:
    """Return roles for a guild sourced from the bot's internal API."""
    ensure_guild_match(guild_id, current_user)
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


@router.get(
    "/{guild_id}/channels/discord",
    response_model=GuildChannelsResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_discord_channels(
    guild_id: int,
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> GuildChannelsResponse:
    """Return text channels for a guild sourced from the bot's internal API."""
    ensure_guild_match(guild_id, current_user)
    try:
        channels_payload = await internal_api.get_guild_channels(guild_id)
    except Exception as exc:  # pragma: no cover - transport errors
        raise translate_internal_api_error(exc, "Failed to fetch channels") from exc

    channels: list[DiscordChannel] = []
    for channel in channels_payload:
        channel_id = channel.get("id")
        if channel_id:
            channels.append(
                DiscordChannel(
                    id=str(channel_id),
                    name=channel.get("name", "Unknown"),
                    category=channel.get("category"),
                    position=channel.get("position", 0),
                    type=safe_int(channel.get("type")),
                )
            )

    return GuildChannelsResponse(channels=channels)


@router.get(
    "/{guild_id}/members",
    response_model=GuildMembersResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def list_guild_members(
    guild_id: int,
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(100, ge=1, le=1000),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> GuildMembersResponse:
    """Proxy paginated Discord member data from the bot's internal API."""
    ensure_guild_match(guild_id, current_user)

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
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_guild_member_detail(
    guild_id: int,
    user_id: int,
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> GuildMemberResponse:
    """Proxy a single Discord member lookup via the internal API."""
    ensure_guild_match(guild_id, current_user)

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
