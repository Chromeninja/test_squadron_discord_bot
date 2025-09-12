"""
Utilities Package

Common utilities and helper functions for the Discord bot.
"""

from .errors import BotError, ConfigError, DatabaseError, ServiceError
from .logging import get_logger, setup_logging
from .tasks import spawn, wait_for_any
from .types import (
    ChannelId,
    CleanupResult,
    GuildConfig,
    GuildId,
    LogLevel,
    MessageId,
    RoleId,
    ServiceStatus,
    UserId,
    VoiceChannelInfo,
    VoiceChannelResult,
)

__all__ = [
    "BotError",
    "ChannelId",
    "CleanupResult",
    "ConfigError",
    "DatabaseError",
    "GuildConfig",
    "GuildId",
    "LogLevel",
    "MessageId",
    "RoleId",
    "ServiceError",
    "ServiceStatus",
    "UserId",
    "VoiceChannelInfo",
    "VoiceChannelResult",
    "get_logger",
    "setup_logging",
    "spawn",
    "wait_for_any"
]
