"""
Pydantic schemas for API request/response models.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Auth schemas
class GuildPermission(BaseModel):
    """Permission level for a specific guild.

    Role hierarchy (highest to lowest):
    - bot_owner: Bot owner (global access)
    - bot_admin: Bot administrator
    - discord_manager: Discord manager (can reset verification, manage voice)
    - moderator: Moderator (read-only access)
    - staff: Staff member (basic privileges)
    - user: Regular user (no special privileges)
    """

    guild_id: str
    role_level: (
        str  # One of: bot_owner, bot_admin, discord_manager, moderator, staff, user
    )
    source: str  # How permission was granted: bot_owner, discord_owner, discord_administrator, bot_admin_role, discord_manager_role, moderator_role, staff_role


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
    # Cross-guild mode: guild name for display
    guild_name: str | None = None


class GuildVoiceGroup(BaseModel):
    """Voice channels grouped by guild for cross-guild view."""

    guild_id: str
    guild_name: str
    items: list[ActiveVoiceChannel] = Field(default_factory=list)


class ActiveVoiceChannelsResponse(BaseModel):
    """Response for /api/voice/active endpoint."""

    success: bool = True
    items: list[ActiveVoiceChannel]
    total: int
    is_cross_guild: bool = False
    guild_groups: list[GuildVoiceGroup] | None = None  # Populated in cross-guild mode


class PermissionEntry(BaseModel):
    """Permission setting for a target (role or user)."""

    target_id: str  # Changed to str to preserve 64-bit Discord snowflake precision
    target_type: str
    permission: str
    target_name: str | None = None
    is_everyone: bool = False
    unknown_role: bool = False


class PTTSettingEntry(BaseModel):
    """Push-to-talk setting for a target."""

    target_id: str  # Changed to str to preserve 64-bit Discord snowflake precision
    target_type: str
    ptt_enabled: bool
    target_name: str | None = None
    is_everyone: bool = False
    unknown_role: bool = False


class PrioritySpeakerEntry(BaseModel):
    """Priority speaker setting for a target."""

    target_id: str  # Changed to str to preserve 64-bit Discord snowflake precision
    target_type: str
    priority_enabled: bool
    target_name: str | None = None
    is_everyone: bool = False
    unknown_role: bool = False


class SoundboardEntry(BaseModel):
    """Soundboard setting for a target."""

    target_id: str  # Changed to str to preserve 64-bit Discord snowflake precision
    target_type: str
    soundboard_enabled: bool
    target_name: str | None = None
    is_everyone: bool = False
    unknown_role: bool = False


class JTCChannelSettings(BaseModel):
    """Settings for a single JTC channel."""

    jtc_channel_id: str  # Changed to str to preserve 64-bit Discord snowflake precision
    jtc_channel_name: str | None = None  # Display name of the JTC channel
    channel_name: str | None = None
    user_limit: int | None = None
    lock: bool = False
    permissions: list[PermissionEntry] = Field(default_factory=list)
    ptt_settings: list[PTTSettingEntry] = Field(default_factory=list)
    priority_settings: list[PrioritySpeakerEntry] = Field(default_factory=list)
    soundboard_settings: list[SoundboardEntry] = Field(default_factory=list)


class UserJTCSettings(BaseModel):
    """User's JTC settings summary."""

    user_id: str  # Changed to str to preserve 64-bit Discord snowflake precision
    rsi_handle: str | None = None
    community_moniker: str | None = None
    primary_jtc_id: str | None = (
        None  # Changed to str to preserve 64-bit Discord snowflake precision
    )
    jtcs: list[JTCChannelSettings] = Field(default_factory=list)
    # Cross-guild mode: guild info for grouping
    guild_id: str | None = None
    guild_name: str | None = None


class GuildUserSettingsGroup(BaseModel):
    """User voice settings grouped by guild for cross-guild view."""

    guild_id: str
    guild_name: str
    items: list[UserJTCSettings] = Field(default_factory=list)


class VoiceUserSettingsSearchResponse(BaseModel):
    """Response for /api/voice/user-settings search endpoint."""

    success: bool = True
    items: list[UserJTCSettings] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    message: str | None = None
    is_cross_guild: bool = False
    guild_groups: list[GuildUserSettingsGroup] | None = None  # Populated in cross-guild mode


class VoiceSettingsResetResponse(BaseModel):
    """Response for voice settings reset operation."""

    success: bool = True
    message: str
    channel_deleted: bool = False
    channel_id: int | None = None
    deleted_counts: dict[str, int] = Field(default_factory=dict)


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

    id: str  # Changed to str to preserve 64-bit Discord snowflake precision
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


class RoleDelegationPolicy(BaseModel):
    """Delegation policy describing who can grant which role under prerequisites."""

    grantor_role_ids: list[str] = Field(default_factory=list)
    target_role_id: str
    prerequisite_role_ids_all: list[str] = Field(default_factory=list)
    prerequisite_role_ids_any: list[str] = Field(default_factory=list)
    # Compatibility field; populated from *_all for older clients when present.
    prerequisite_role_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    note: str | None = None


class BotRoleSettings(BaseModel):
    """Bot permission role assignments, member category roles, and delegation policies.

    Permission roles (managed via web admin):
    - bot_admins: Full bot administration access
    - discord_managers: Can reset verification, manage voice, view all users
    - moderators: Read-only access to user/voice info
    - staff: Basic staff privileges

    Verification roles (assigned by verification system):
    - bot_verified_role: Base verification role (all users who complete RSI verification)
    - main_role: Main organization members
    - affiliate_role: Affiliate organization members
    - nonmember_role: Non-members who have verified
    """

    # All role IDs are strings to preserve 64-bit Discord snowflake precision
    bot_admins: list[str] = Field(default_factory=list)
    discord_managers: list[str] = Field(default_factory=list)
    moderators: list[str] = Field(default_factory=list)
    staff: list[str] = Field(default_factory=list)
    bot_verified_role: list[str] = Field(default_factory=list)
    main_role: list[str] = Field(default_factory=list)
    affiliate_role: list[str] = Field(default_factory=list)
    nonmember_role: list[str] = Field(default_factory=list)

    delegation_policies: list[RoleDelegationPolicy] = Field(default_factory=list)


class VoiceSelectableRoles(BaseModel):
    """Selectable voice role configuration for channel automation."""

    # Role IDs are strings to preserve 64-bit Discord snowflake precision
    selectable_roles: list[str] = Field(default_factory=list)


class MetricsSettings(BaseModel):
    """Guild-scoped metrics collection settings."""

    excluded_channel_ids: list[str] = Field(default_factory=list)
    tracked_games_mode: str = Field(default="all")  # "all" or "specific"
    tracked_games: list[str] = Field(default_factory=list)
    min_voice_minutes: int = Field(default=15, ge=0, le=1440)
    min_game_minutes: int = Field(default=15, ge=0, le=1440)
    min_messages: int = Field(default=5, ge=0, le=10000)


class NewMemberRoleSettings(BaseModel):
    """Per-guild new-member role module configuration.

    When enabled, a configurable role is assigned on first verification
    and automatically removed after ``duration_days``.  An optional
    ``max_server_age_days`` gate skips assignment for members who joined
    more than N days ago (null = no gate).
    """

    enabled: bool = False
    role_id: str | None = None  # Discord role snowflake (string for precision)
    duration_days: int = Field(default=14, ge=1)
    max_server_age_days: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_enabled_requires_role(self) -> "NewMemberRoleSettings":
        if self.enabled and not self.role_id:
            raise ValueError("role_id is required when new-member role is enabled")
        return self


class RoleDelegationConfig(BaseModel):
    """Collection of delegation policies for a guild (compat endpoint wrapper)."""

    policies: list[RoleDelegationPolicy] = Field(default_factory=list)


class RoleDelegationConfigResponse(BaseModel):
    """Response wrapper for delegation policy config."""

    success: bool = True
    data: RoleDelegationConfig


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


class BotChannelSettingsResponse(BaseModel):
    """Response wrapper for bot channel settings with operation metadata."""

    verification_channel_id: str | None = None
    bot_spam_channel_id: str | None = None
    public_announcement_channel_id: str | None = None
    leadership_announcement_channel_id: str | None = None
    verification_message_updated: bool | None = None  # None if not applicable, True/False if attempted


class OrganizationSettings(BaseModel):
    """Organization configuration for guild verification."""

    organization_sid: str | None = None
    organization_name: str | None = None
    organization_logo_url: str | None = None


class OrganizationSettingsResponse(BaseModel):
    """Response wrapper for organization settings with operation metadata."""

    organization_sid: str | None = None
    organization_name: str | None = None
    organization_logo_url: str | None = None
    verification_message_updated: bool | None = None  # None if not applicable, True/False if attempted


class OrganizationValidationRequest(BaseModel):
    """Request payload for validating an organization SID."""

    sid: str


class OrganizationValidationResponse(BaseModel):
    """Response payload for organization SID validation."""

    success: bool = True
    is_valid: bool
    sid: str
    organization_name: str | None = None
    error: str | None = None


class LogoValidationRequest(BaseModel):
    """Request payload for validating a logo URL."""

    url: str


class LogoValidationResponse(BaseModel):
    """Response payload for logo URL validation."""

    success: bool = True
    is_valid: bool
    url: str | None = None
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
    metrics: MetricsSettings
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
    metrics: MetricsSettings | None = None
    organization: OrganizationSettings | None = None


# ============================================================================
# Metrics schemas
# ============================================================================


class MetricsLive(BaseModel):
    """Live snapshot of current metrics."""

    messages_today: int = 0
    active_voice_users: int = 0
    active_game_sessions: int = 0
    top_game: str | None = None


class MetricsPeriod(BaseModel):
    """Aggregated metrics for a time period."""

    total_messages: int = 0
    unique_messagers: int = 0
    avg_messages_per_user: float = 0.0
    total_voice_seconds: int = 0
    unique_voice_users: int = 0
    avg_voice_per_user: int = 0
    unique_users: int = 0
    top_games: list[dict] = []


class MetricsOverview(BaseModel):
    """Combined live + period metrics overview."""

    live: MetricsLive
    period: MetricsPeriod


class MetricsOverviewResponse(BaseModel):
    """Response for /api/metrics/overview."""

    success: bool = True
    data: MetricsOverview


class VoiceLeaderboardEntry(BaseModel):
    """Single entry in voice time leaderboard."""

    user_id: str
    total_seconds: int
    username: str | None = None
    avatar_url: str | None = None


class MessageLeaderboardEntry(BaseModel):
    """Single entry in message count leaderboard."""

    user_id: str
    total_messages: int
    username: str | None = None
    avatar_url: str | None = None


class LeaderboardResponse(BaseModel):
    """Response for leaderboard endpoints."""

    success: bool = True
    entries: list[dict]


class GameStats(BaseModel):
    """Stats for a single game."""

    game_name: str
    total_seconds: int
    session_count: int
    avg_seconds: int = 0
    unique_players: int = 0


class TopGamesResponse(BaseModel):
    """Response for /api/metrics/games/top."""

    success: bool = True
    games: list[GameStats]


class TimeSeriesPoint(BaseModel):
    """Single data point in a time series."""

    timestamp: int
    value: int | None = None
    unique_users: int | None = None
    top_game: str | None = None


class TimeSeriesResponse(BaseModel):
    """Response for /api/metrics/timeseries."""

    success: bool = True
    metric: str
    days: int
    data: list[dict]


class UserGameStats(BaseModel):
    """Per-user game breakdown."""

    game_name: str
    total_seconds: int


class UserTimeSeriesPoint(BaseModel):
    """Per-user time series point."""

    timestamp: int
    messages: int = 0
    voice_seconds: int = 0


class UserMetrics(BaseModel):
    """Detailed metrics for a single user."""

    user_id: str
    username: str | None = None
    avatar_url: str | None = None
    total_messages: int = 0
    total_voice_seconds: int = 0
    avg_messages_per_day: float = 0.0
    avg_voice_per_day: int = 0
    top_games: list[UserGameStats] = []
    timeseries: list[UserTimeSeriesPoint] = []
    # Per-dimension activity tiers
    voice_tier: str | None = None
    chat_tier: str | None = None
    game_tier: str | None = None
    combined_tier: str | None = None
    last_voice_at: int | None = None
    last_chat_at: int | None = None
    last_game_at: int | None = None


class UserMetricsResponse(BaseModel):
    """Response for /api/metrics/user/{user_id}."""

    success: bool = True
    data: UserMetrics


class ActivityTierCounts(BaseModel):
    """Counts of members per activity tier for one dimension."""

    hardcore: int = 0
    regular: int = 0
    casual: int = 0
    reserve: int = 0
    inactive: int = 0


class ActivityGroupCounts(BaseModel):
    """Per-dimension activity group counts."""

    model_config = ConfigDict(populate_by_name=True)

    all: ActivityTierCounts = Field(default_factory=ActivityTierCounts, validation_alias="combined")
    voice: ActivityTierCounts = Field(default_factory=ActivityTierCounts)
    chat: ActivityTierCounts = Field(default_factory=ActivityTierCounts)
    game: ActivityTierCounts = Field(default_factory=ActivityTierCounts)


class ActivityGroupCountsResponse(BaseModel):
    """Response for /api/metrics/activity-groups."""

    success: bool = True
    data: ActivityGroupCounts
