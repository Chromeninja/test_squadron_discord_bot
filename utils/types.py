"""
Type definitions and common data structures for the Discord bot.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple


class VoiceChannelResult(NamedTuple):
    """Result of voice channel operation."""

    success: bool
    channel_id: int | None = None
    channel_mention: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None  # For error-specific data like owner_display


@dataclass
class VoiceChannelInfo:
    """Information about a voice channel."""

    guild_id: int
    jtc_channel_id: int
    channel_id: int
    owner_id: int
    created_at: int
    last_activity: int
    is_active: bool = True


@dataclass
class TargetEntry:
    """A single target (role/user/@everyone) with settings."""

    target_id: str  # String to preserve 64-bit Discord snowflake precision
    target_type: str  # "role" or "user"
    target_name: str | None = None
    is_everyone: bool = False
    unknown_role: bool = False


@dataclass
class PermissionOverride(TargetEntry):
    """Permission override for a target."""

    permission: str = "permit"  # "permit" or "deny"


@dataclass
class PTTSetting(TargetEntry):
    """Push-to-talk setting for a target."""

    ptt_enabled: bool = False


@dataclass
class PrioritySpeakerSetting(TargetEntry):
    """Priority speaker setting for a target."""

    priority_enabled: bool = False


@dataclass
class SoundboardSetting(TargetEntry):
    """Soundboard setting for a target."""

    soundboard_enabled: bool = False


@dataclass
class VoiceSettingsSnapshot:
    """Complete snapshot of voice channel settings.

    This unified data model is used by:
    - /voice list and /voice admin_list commands
    - Backend API endpoints (/api/voice/search, /api/voice/active, /api/voice/user-settings)
    - Dashboard UI

    All voice listing logic should use this snapshot to ensure consistency.
    """

    guild_id: int
    jtc_channel_id: int
    owner_id: int
    voice_channel_id: int | None = None  # None if not currently active
    channel_name: str | None = None
    user_limit: int | None = None
    is_locked: bool = False
    created_at: int | None = None
    last_activity: int | None = None
    is_active: bool = False  # Whether user is currently in the channel

    # Settings lists with resolved names
    permissions: list[PermissionOverride] = field(default_factory=list)
    ptt_settings: list[PTTSetting] = field(default_factory=list)
    priority_speaker_settings: list[PrioritySpeakerSetting] = field(default_factory=list)
    soundboard_settings: list[SoundboardSetting] = field(default_factory=list)


@dataclass
class GuildConfig:
    """Guild-specific configuration."""

    guild_id: int
    voice_category_id: int | None = None
    jtc_channel_ids: list[int] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Initialization is now handled by field(default_factory=...)
        pass


class ServiceStatus(Enum):
    """Service initialization status."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"


class LogLevel(Enum):
    """Log level enumeration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Type aliases
GuildId = int
UserId = int
ChannelId = int
MessageId = int
RoleId = int
