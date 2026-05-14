"""Guild configuration and settings schemas."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    - event_coordinators: Event management access above staff, below moderator
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
    event_coordinators: list[str] = Field(default_factory=list)
    staff: list[str] = Field(default_factory=list)
    bot_verified_role: list[str] = Field(default_factory=list)
    main_role: list[str] = Field(default_factory=list)
    affiliate_role: list[str] = Field(default_factory=list)
    nonmember_role: list[str] = Field(default_factory=list)

    delegation_policies: list[RoleDelegationPolicy] = Field(default_factory=list)


class EventModuleSettings(BaseModel):
    """Guild-scoped event module configuration."""

    enabled: bool = True
    default_native_sync: bool = True
    default_announcement_channel_id: str | None = None
    default_voice_channel_id: str | None = None


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
    type: int | None = None


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
    verification_message_updated: bool | None = (
        None  # None if not applicable, True/False if attempted
    )


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
    verification_message_updated: bool | None = (
        None  # None if not applicable, True/False if attempted
    )


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
    events: EventModuleSettings
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
    events: EventModuleSettings | None = None
