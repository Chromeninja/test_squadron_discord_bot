"""Auth and user schemas."""

from pydantic import BaseModel, Field


class GuildPermission(BaseModel):
    """Permission level for a specific guild.

    Role hierarchy (highest to lowest):
    - bot_owner: Bot owner (global access)
    - bot_admin: Bot administrator
    - discord_manager: Discord manager (can reset verification, manage voice)
    - event_coordinator: Event operations access above staff, below moderator
    - moderator: Moderator (read-only access)
    - staff: Staff member (basic privileges)
    - user: Regular user (no special privileges)
    """

    guild_id: str
    role_level: (
        str  # One of: bot_owner, bot_admin, discord_manager, event_coordinator, moderator, staff, user
    )
    source: str  # How permission was granted: bot_owner, discord_owner, discord_administrator, bot_admin_role, discord_manager_role, event_coordinator_role, moderator_role, staff_role


class UserProfile(BaseModel):
    """Authenticated user profile with per-guild permissions."""

    user_id: str
    username: str
    discriminator: str
    avatar: str | None = None
    authorized_guilds: dict[str, GuildPermission] = Field(
        default_factory=dict
    )  # guild_id -> GuildPermission mapping
    active_guild_id: str | None = None
    is_bot_owner: bool = False  # True if user is in bot owner IDs list


class AuthMeResponse(BaseModel):
    """Response for /api/auth/me endpoint."""

    success: bool = True
    user: UserProfile | None = None


class GuildSummary(BaseModel):
    """Minimal guild information for selection UI."""

    guild_id: str
    guild_name: str
    icon_url: str | None = None


class GuildListResponse(BaseModel):
    """Response for /api/auth/guilds endpoint."""

    success: bool = True
    guilds: list[GuildSummary]


class SelectGuildRequest(BaseModel):
    """Request payload for selecting an active guild."""

    guild_id: str


class SelectGuildResponse(BaseModel):
    """Response payload when a guild selection succeeds."""

    success: bool = True
