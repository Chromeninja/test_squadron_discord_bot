"""Typed configuration schema for the Discord bot application."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ChannelsConfig:
    """Configuration for Discord channel IDs."""
    verification_channel_id: int
    public_announcement_channel_id: int
    leadership_announcement_channel_id: int
    bot_spam_channel_id: Optional[int] = None


@dataclass
class RolesConfig:
    """Configuration for Discord role IDs."""
    bot_verified_role_id: int
    main_role_id: int
    affiliate_role_id: int
    non_member_role_id: int
    bot_admins: List[str] = field(default_factory=list)
    lead_moderators: List[str] = field(default_factory=list)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting settings."""
    max_attempts: int = 5
    window_seconds: int = 1800  # 30 minutes
    recheck_window_seconds: int = 300  # 5 minutes
    task_queue_workers: int = 1  # Default worker count
    api_max_rate: int = 45  # API requests per time period
    api_time_period: int = 1  # Time period in seconds


@dataclass
class BulkAnnouncementConfig:
    """Configuration for bulk announcement system."""
    hour_utc: int = 21
    minute_utc: int = 0
    threshold: int = 50
    max_mentions_per_message: int = 50
    max_chars_per_message: int = 1800


@dataclass
class LoggingConfig:
    """Configuration for logging settings."""
    level: str = "INFO"

    def __post_init__(self):
        """Validate logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.level.upper() not in valid_levels:
            self.level = "INFO"


@dataclass
class HTTPClientConfig:
    """Configuration for HTTP client settings."""
    user_agent: str = "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)"
    requests_per_minute: int = 30


@dataclass
class BotConfig:
    """Configuration for bot-specific settings."""
    prefix: List[str] = field(default_factory=list)


@dataclass
class OrganizationConfig:
    """Configuration for organization information."""
    name: str = "TEST Squadron - Best Squardon!"


@dataclass
class VoiceConfig:
    """Configuration for voice channel settings."""
    cooldown_seconds: int = 5
    expiry_days: int = 30
    join_to_create_channels: Dict[str, List[int]] = field(default_factory=dict)


@dataclass
class DatabaseConfig:
    """Configuration for database settings."""
    path: str = "TESTDatabase.db"


@dataclass
class RSIConfig:
    """Configuration for RSI API settings."""
    user_agent: str = "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)"
    requests_per_minute: int = 30


@dataclass
class AutoRecheckCadenceConfig:
    """Configuration for auto-recheck cadence by role."""
    main: int = 1
    affiliate: int = 1
    non_member: int = 1


@dataclass
class AutoRecheckBatchConfig:
    """Configuration for auto-recheck batch processing."""
    run_every_minutes: int = 1
    max_users_per_run: int = 50


@dataclass
class AutoRecheckBackoffConfig:
    """Configuration for auto-recheck backoff settings."""
    base_minutes: int = 180  # 3 hours
    max_minutes: int = 1440  # 24 hours


@dataclass
class AutoRecheckConfig:
    """Configuration for auto-recheck system."""
    enabled: bool = True
    jitter_hours: int = 12
    cadence_days: AutoRecheckCadenceConfig = field(default_factory=AutoRecheckCadenceConfig)
    batch: AutoRecheckBatchConfig = field(default_factory=AutoRecheckBatchConfig)
    backoff: AutoRecheckBackoffConfig = field(default_factory=AutoRecheckBackoffConfig)


@dataclass
class AppConfig:
    """Main application configuration containing all subsections."""
    channels: ChannelsConfig
    roles: RolesConfig
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    bulk_announcement: BulkAnnouncementConfig = field(default_factory=BulkAnnouncementConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    http_client: HTTPClientConfig = field(default_factory=HTTPClientConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    organization: OrganizationConfig = field(default_factory=OrganizationConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    rsi: RSIConfig = field(default_factory=RSIConfig)
    auto_recheck: AutoRecheckConfig = field(default_factory=AutoRecheckConfig)
    selectable_roles: List[int] = field(default_factory=list)

    # Raw config dict for backward compatibility
    _raw_config: Dict[str, Any] = field(default_factory=dict, repr=False)

    def get_raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary for backward compatibility."""
        return self._raw_config
