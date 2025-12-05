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
