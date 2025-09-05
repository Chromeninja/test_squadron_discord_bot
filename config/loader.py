"""Configuration loader with validation for the Discord bot application."""

import yaml
import logging
from typing import Dict, Any
from .schema import (
    AppConfig, ChannelsConfig, RolesConfig, RateLimitConfig,
    BulkAnnouncementConfig, LoggingConfig, HTTPClientConfig,
    BotConfig, OrganizationConfig, VoiceConfig, DatabaseConfig,
    RSIConfig, AutoRecheckConfig, AutoRecheckCadenceConfig,
    AutoRecheckBatchConfig, AutoRecheckBackoffConfig
)


logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """
    Load and validate configuration from YAML file with environment overrides.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        AppConfig: Validated configuration instance
        
    Raises:
        ConfigValidationError: If required configuration is missing or invalid
    """
    # Load base YAML config
    raw_config = _load_yaml_config(config_path)
    
    # Apply environment overrides
    raw_config = _apply_environment_overrides(raw_config)
    
    # Validate and create typed config
    app_config = _create_app_config(raw_config)
    
    # Store raw config for backward compatibility
    app_config._raw_config = raw_config
    
    return app_config


def _load_yaml_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
            
        if not isinstance(config, dict):
            logger.warning("Configuration file did not contain a mapping; using empty config.")
            return {}
            
        logger.info("Configuration loaded successfully from %s", config_path)
        return config
        
    except FileNotFoundError:
        logger.warning("Configuration file not found at path: %s; using empty config.", config_path)
        return {}
    except yaml.YAMLError as e:
        logger.error("Error parsing configuration file: %s; using empty config.", e)
        return {}
    except UnicodeDecodeError as e:
        logger.error("Encoding error while reading configuration file: %s; using empty config.", e)
        return {}


def _apply_environment_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to configuration."""
    # For now, we'll keep this simple and just return the config as-is
    # In the future, we could add specific environment overrides here
    return config


def _create_app_config(raw_config: Dict[str, Any]) -> AppConfig:
    """Create and validate AppConfig from raw configuration."""
    
    # Validate and create required configurations
    try:
        channels_config = _create_channels_config(raw_config.get("channels", {}))
        roles_config = _create_roles_config(raw_config.get("roles", {}))
        
        # Create optional configurations with defaults
        rate_limits_config = _create_rate_limits_config(raw_config.get("rate_limits", {}))
        bulk_announcement_config = _create_bulk_announcement_config(raw_config.get("bulk_announcement", {}))
        logging_config = _create_logging_config(raw_config.get("logging", {}))
        http_client_config = _create_http_client_config(raw_config.get("rsi", {}))
        bot_config = _create_bot_config(raw_config.get("bot", {}))
        organization_config = _create_organization_config(raw_config.get("organization", {}))
        voice_config = _create_voice_config(raw_config.get("voice", {}))
        database_config = _create_database_config(raw_config.get("database", {}))
        rsi_config = _create_rsi_config(raw_config.get("rsi", {}))
        auto_recheck_config = _create_auto_recheck_config(raw_config.get("auto_recheck", {}))
        
        # Handle selectable roles
        selectable_roles = _convert_to_int_list(raw_config.get("selectable_roles", []), "selectable_roles")
        
        return AppConfig(
            channels=channels_config,
            roles=roles_config,
            rate_limits=rate_limits_config,
            bulk_announcement=bulk_announcement_config,
            logging=logging_config,
            http_client=http_client_config,
            bot=bot_config,
            organization=organization_config,
            voice=voice_config,
            database=database_config,
            rsi=rsi_config,
            auto_recheck=auto_recheck_config,
            selectable_roles=selectable_roles
        )
        
    except Exception as e:
        raise ConfigValidationError(f"Configuration validation failed: {e}") from e


def _create_channels_config(channels_data: Dict[str, Any]) -> ChannelsConfig:
    """Create and validate ChannelsConfig."""
    required_fields = [
        "verification_channel_id",
        "public_announcement_channel_id", 
        "leadership_announcement_channel_id"
    ]
    
    for field in required_fields:
        if field not in channels_data:
            raise ConfigValidationError(f"Required channel configuration missing: {field}")
    
    return ChannelsConfig(
        verification_channel_id=_convert_to_int(channels_data["verification_channel_id"], "verification_channel_id"),
        public_announcement_channel_id=_convert_to_int(channels_data["public_announcement_channel_id"], "public_announcement_channel_id"),
        leadership_announcement_channel_id=_convert_to_int(channels_data["leadership_announcement_channel_id"], "leadership_announcement_channel_id"),
        bot_spam_channel_id=_convert_to_int(channels_data.get("bot_spam_channel_id"), "bot_spam_channel_id") if channels_data.get("bot_spam_channel_id") is not None else None
    )


def _create_roles_config(roles_data: Dict[str, Any]) -> RolesConfig:
    """Create and validate RolesConfig."""
    required_fields = [
        "bot_verified_role_id",
        "main_role_id",
        "affiliate_role_id",
        "non_member_role_id"
    ]
    
    for field in required_fields:
        if field not in roles_data:
            raise ConfigValidationError(f"Required role configuration missing: {field}")
    
    return RolesConfig(
        bot_verified_role_id=_convert_to_int(roles_data["bot_verified_role_id"], "bot_verified_role_id"),
        main_role_id=_convert_to_int(roles_data["main_role_id"], "main_role_id"),
        affiliate_role_id=_convert_to_int(roles_data["affiliate_role_id"], "affiliate_role_id"),
        non_member_role_id=_convert_to_int(roles_data["non_member_role_id"], "non_member_role_id"),
        bot_admins=roles_data.get("bot_admins", []),
        lead_moderators=roles_data.get("lead_moderators", [])
    )


def _create_rate_limits_config(rate_limits_data: Dict[str, Any]) -> RateLimitConfig:
    """Create RateLimitConfig with defaults."""
    return RateLimitConfig(
        max_attempts=rate_limits_data.get("max_attempts", 5),
        window_seconds=rate_limits_data.get("window_seconds", 1800),
        recheck_window_seconds=rate_limits_data.get("recheck_window_seconds", 300),
        task_queue_workers=rate_limits_data.get("task_queue_workers", 1)
    )


def _create_bulk_announcement_config(bulk_data: Dict[str, Any]) -> BulkAnnouncementConfig:
    """Create BulkAnnouncementConfig with defaults."""
    return BulkAnnouncementConfig(
        hour_utc=bulk_data.get("hour_utc", 21),
        minute_utc=bulk_data.get("minute_utc", 0),
        threshold=bulk_data.get("threshold", 50),
        max_mentions_per_message=bulk_data.get("max_mentions_per_message", 50),
        max_chars_per_message=bulk_data.get("max_chars_per_message", 1800)
    )


def _create_logging_config(logging_data: Dict[str, Any]) -> LoggingConfig:
    """Create LoggingConfig with validation."""
    return LoggingConfig(
        level=logging_data.get("level", "INFO")
    )


def _create_http_client_config(rsi_data: Dict[str, Any]) -> HTTPClientConfig:
    """Create HTTPClientConfig from RSI config section."""
    return HTTPClientConfig(
        user_agent=rsi_data.get("user_agent", "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)"),
        requests_per_minute=rsi_data.get("requests_per_minute", 30)
    )


def _create_bot_config(bot_data: Dict[str, Any]) -> BotConfig:
    """Create BotConfig with defaults."""
    return BotConfig(
        prefix=bot_data.get("prefix", [])
    )


def _create_organization_config(org_data: Dict[str, Any]) -> OrganizationConfig:
    """Create OrganizationConfig with defaults."""
    return OrganizationConfig(
        name=org_data.get("name", "TEST Squadron - Best Squardon!")
    )


def _create_voice_config(voice_data: Dict[str, Any]) -> VoiceConfig:
    """Create VoiceConfig with defaults."""
    return VoiceConfig(
        cooldown_seconds=voice_data.get("cooldown_seconds", 5),
        expiry_days=voice_data.get("expiry_days", 30)
    )


def _create_database_config(db_data: Dict[str, Any]) -> DatabaseConfig:
    """Create DatabaseConfig with defaults."""
    return DatabaseConfig(
        path=db_data.get("path", "TESTDatabase.db")
    )


def _create_rsi_config(rsi_data: Dict[str, Any]) -> RSIConfig:
    """Create RSIConfig with defaults."""
    return RSIConfig(
        user_agent=rsi_data.get("user_agent", "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)"),
        requests_per_minute=rsi_data.get("requests_per_minute", 30)
    )


def _create_auto_recheck_config(auto_recheck_data: Dict[str, Any]) -> AutoRecheckConfig:
    """Create AutoRecheckConfig with defaults."""
    cadence_data = auto_recheck_data.get("cadence_days", {})
    batch_data = auto_recheck_data.get("batch", {})
    backoff_data = auto_recheck_data.get("backoff", {})
    
    return AutoRecheckConfig(
        enabled=auto_recheck_data.get("enabled", True),
        jitter_hours=auto_recheck_data.get("jitter_hours", 12),
        cadence_days=AutoRecheckCadenceConfig(
            main=cadence_data.get("main", 1),
            affiliate=cadence_data.get("affiliate", 1),
            non_member=cadence_data.get("non_member", 1)
        ),
        batch=AutoRecheckBatchConfig(
            run_every_minutes=batch_data.get("run_every_minutes", 1),
            max_users_per_run=batch_data.get("max_users_per_run", 50)
        ),
        backoff=AutoRecheckBackoffConfig(
            base_minutes=backoff_data.get("base_minutes", 180),
            max_minutes=backoff_data.get("max_minutes", 1440)
        )
    )


def _convert_to_int(value: Any, field_name: str) -> int:
    """Convert value to int with helpful error message."""
    if value is None:
        raise ConfigValidationError(f"Field '{field_name}' cannot be None")
    
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ConfigValidationError(f"Field '{field_name}' must be an integer, got: {value}")


def _convert_to_int_list(value: Any, field_name: str) -> list[int]:
    """Convert value to list of ints with helpful error message."""
    if not isinstance(value, list):
        raise ConfigValidationError(f"Field '{field_name}' must be a list, got: {type(value)}")
    
    try:
        return [int(item) for item in value]
    except (ValueError, TypeError):
        raise ConfigValidationError(f"All items in '{field_name}' must be integers")
