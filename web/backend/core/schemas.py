"""
Pydantic schemas for API request/response models.
"""

from pydantic import BaseModel, Field


# Auth schemas
class UserProfile(BaseModel):
    """Authenticated user profile."""

    user_id: str
    username: str
    discriminator: str
    avatar: str | None = None
    is_admin: bool
    is_moderator: bool
    authorized_guild_ids: list[int] = Field(default_factory=list)
    active_guild_id: str | None = None
    permission_sources: dict[str, str] = Field(default_factory=dict)  # guild_id (str) -> source (owner/administrator/bot_admin_role/moderator_role)


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


# Stats schemas
class StatusCounts(BaseModel):
    """Verification status breakdown."""

    main: int = 0
    affiliate: int = 0
    non_member: int = 0
    unknown: int = 0


class StatsOverview(BaseModel):
    """Dashboard statistics overview."""

    total_verified: int
    by_status: StatusCounts
    voice_active_count: int


class StatsResponse(BaseModel):
    """Response for /api/stats/overview."""

    success: bool = True
    data: StatsOverview


# Health schemas
class SystemMetrics(BaseModel):
    """System resource metrics."""

    cpu_percent: float
    memory_percent: float


class HealthOverview(BaseModel):
    """Bot health overview for dashboard."""

    status: str  # "healthy", "degraded", "unhealthy"
    uptime_seconds: int
    db_ok: bool
    discord_latency_ms: float | None = None
    system: SystemMetrics


class HealthResponse(BaseModel):
    """Response for /api/health/overview."""

    success: bool = True
    data: HealthOverview


# Error schemas
class StructuredError(BaseModel):
    """Structured error log entry."""

    time: str
    error_type: str
    component: str
    message: str | None = None
    traceback: str | None = None


class ErrorsResponse(BaseModel):
    """Response for /api/errors/last."""

    success: bool = True
    errors: list[StructuredError]


# User schemas
class VerificationRecord(BaseModel):
    """User verification record."""

    user_id: int
    rsi_handle: str
    membership_status: str | None = None
    community_moniker: str | None = None
    last_updated: int
    needs_reverify: bool = False
    main_orgs: list[str] | None = None
    affiliate_orgs: list[str] | None = None


class UserSearchResponse(BaseModel):
    """Response for /api/users/search."""

    success: bool = True
    items: list[VerificationRecord]
    total: int
    page: int
    page_size: int


# Voice schemas
class VoiceChannelRecord(BaseModel):
    """Voice channel record."""

    id: int
    guild_id: int
    jtc_channel_id: int
    owner_id: int
    voice_channel_id: int
    created_at: int
    last_activity: int
    is_active: bool


class VoiceSearchResponse(BaseModel):
    """Response for /api/voice/search."""

    success: bool = True
    items: list[VoiceChannelRecord]
    total: int


class VoiceChannelMember(BaseModel):
    """Member information for a voice channel."""

    user_id: int
    username: str | None = None
    display_name: str | None = None
    rsi_handle: str | None = None
    membership_status: str | None = None
    is_owner: bool = False


class ActiveVoiceChannel(BaseModel):
    """Active voice channel with owner and member information."""

    voice_channel_id: int
    guild_id: int
    jtc_channel_id: int
    owner_id: int
    owner_username: str | None = None
    owner_rsi_handle: str | None = None
    owner_membership_status: str | None = None
    created_at: int
    last_activity: int
    channel_name: str | None = None
    members: list[VoiceChannelMember] = []


class ActiveVoiceChannelsResponse(BaseModel):
    """Response for /api/voice/active endpoint."""

    success: bool = True
    items: list[ActiveVoiceChannel]
    total: int


# Error schemas
class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized error response."""

    success: bool = False
    error: ErrorDetail


class DiscordRole(BaseModel):
    """Discord role metadata."""

    id: int
    name: str
    color: int | None = None


class GuildRolesResponse(BaseModel):
    """Response for /api/guilds/{guild_id}/roles/discord."""

    success: bool = True
    roles: list[DiscordRole]


class GuildMember(BaseModel):
    """Discord guild member with basic profile and role info."""

    user_id: int
    username: str | None = None
    discriminator: str | None = None
    global_name: str | None = None
    avatar_url: str | None = None
    joined_at: str | None = None
    created_at: str | None = None
    roles: list[DiscordRole] = Field(default_factory=list)


class GuildMembersResponse(BaseModel):
    """Paginated response for guild member listings."""

    success: bool = True
    members: list[GuildMember]
    page: int
    page_size: int
    total: int


class GuildMemberResponse(BaseModel):
    """Response wrapper for a single guild member lookup."""

    success: bool = True
    member: GuildMember


class BotRoleSettings(BaseModel):
    """Bot admin/lead moderator role assignments and member role categories."""

    bot_admins: list[int] = Field(default_factory=list)
    lead_moderators: list[int] = Field(default_factory=list)
    main_role: list[int] = Field(default_factory=list)
    affiliate_role: list[int] = Field(default_factory=list)
    nonmember_role: list[int] = Field(default_factory=list)


class VoiceSelectableRoles(BaseModel):
    """Selectable voice role configuration for channel automation."""

    selectable_roles: list[int] = Field(default_factory=list)


class DiscordChannel(BaseModel):
    """Discord text channel metadata."""

    id: str  # Changed from int to str to preserve 64-bit Discord snowflake precision
    name: str
    category: str | None = None
    position: int


class GuildChannelsResponse(BaseModel):
    """Response for /api/guilds/{guild_id}/channels/discord."""

    success: bool = True
    channels: list[DiscordChannel]


class BotChannelSettings(BaseModel):
    """Bot channel configuration for verification and announcements."""

    verification_channel_id: str | None = None  # Changed to str to preserve precision
    bot_spam_channel_id: str | None = None
    public_announcement_channel_id: str | None = None
    leadership_announcement_channel_id: str | None = None


class OrganizationSettings(BaseModel):
    """Organization configuration for guild verification."""

    organization_sid: str | None = None
    organization_name: str | None = None


class OrganizationValidationRequest(BaseModel):
    """Request payload for validating an organization SID."""

    sid: str


class OrganizationValidationResponse(BaseModel):
    """Response payload for organization SID validation."""

    success: bool = True
    is_valid: bool
    sid: str
    name: str | None = None
    error: str | None = None


# Guild info/config schemas
class GuildInfo(BaseModel):
    """Basic guild identity for page headers."""

    guild_id: str
    guild_name: str
    icon_url: str | None = None


class GuildInfoResponse(BaseModel):
    """Response for /api/guilds/{guild_id}/info."""

    success: bool = True
    guild: GuildInfo


class ReadOnlyYamlConfig(BaseModel):
    """Subset of global YAML config shown read-only in UI."""

    rsi: dict | None = None
    voice: dict | None = None
    voice_debug_logging_enabled: bool | None = None


class GuildConfigData(BaseModel):
    """Combined guild configuration view for settings page."""

    roles: BotRoleSettings
    channels: BotChannelSettings
    voice: VoiceSelectableRoles
    organization: OrganizationSettings
    read_only: ReadOnlyYamlConfig | None = None


class GuildConfigResponse(BaseModel):
    """Response for GET /api/guilds/{guild_id}/config."""

    success: bool = True
    data: GuildConfigData


class GuildConfigUpdateRequest(BaseModel):
    """PATCH payload for updating DB-backed guild settings only."""

    roles: BotRoleSettings | None = None
    channels: BotChannelSettings | None = None
    voice: VoiceSelectableRoles | None = None
    organization: OrganizationSettings | None = None
