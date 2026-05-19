"""Voice channel and settings schemas."""

from pydantic import BaseModel, Field


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
    """Active voice channel with owner and member information.

    For managed (JTC) channels ``is_managed`` is ``True`` and owner / JTC
    metadata is populated.  For unmanaged Discord channels (not created by
    the bot) ``is_managed`` is ``False`` and those fields use defaults.
    """

    voice_channel_id: int
    guild_id: int
    jtc_channel_id: int = 0
    owner_id: int = 0
    owner_username: str | None = None
    owner_rsi_handle: str | None = None
    owner_membership_status: str | None = None
    created_at: int = 0
    last_activity: int = 0
    channel_name: str | None = None
    members: list[VoiceChannelMember] = Field(default_factory=list)
    # Cross-guild mode: guild name for display
    guild_name: str | None = None
    # Whether this channel is managed (JTC) by the bot
    is_managed: bool = True
    # Discord channel type (2=voice, 13=stage)
    channel_type: int | None = None
    # Discord category name
    category: str | None = None


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
    guild_groups: list[GuildUserSettingsGroup] | None = (
        None  # Populated in cross-guild mode
    )


class VoiceSettingsResetResponse(BaseModel):
    """Response for voice settings reset operation."""

    success: bool = True
    message: str
    channel_deleted: bool = False
    channel_id: int | None = None
    deleted_counts: dict[str, int] = Field(default_factory=dict)
