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


class AuthMeResponse(BaseModel):
    """Response for /api/auth/me endpoint."""

    success: bool = True
    user: UserProfile | None = None


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


# User schemas
class VerificationRecord(BaseModel):
    """User verification record."""

    user_id: int
    rsi_handle: str
    membership_status: str | None = None
    community_moniker: str | None = None
    last_updated: int
    needs_reverify: bool = False


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
