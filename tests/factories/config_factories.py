"""
Config Factories

Provides factory functions for creating test configuration objects and files.
Use these to test config loading, validation, and defaults.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Generator


def make_config(
    bot_token: str = "test_token",  # noqa: S107
    prefix: str | list[str] | None = "!",
    logging_level: str = "INFO",
    rsi_org_name: str = "TEST Squadron - Best Squadron!",
    roles: dict[str, Any] | None = None,
    channels: dict[str, Any] | None = None,
    voice: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a configuration dictionary for testing.

    Args:
        token: Discord bot token
        prefix: Command prefix(es)
        logging_level: Logging level string
        rsi_org_name: RSI organization name for verification
        roles: Role configuration dict
        channels: Channel configuration dict
        voice: Voice settings dict
        verification: Verification settings dict
        extra: Additional top-level keys to merge

    Returns:
        Complete configuration dictionary.

    Examples:
        # Basic config
        config = make_config()

        # Config with custom roles
        config = make_config(roles={"bot_admins": [123456789]})

        # Config with verification settings
        config = make_config(verification={"recheck_interval": 3600})
    """
    config: dict[str, Any] = {
        "token": bot_token,
        "prefix": prefix,
        "logging": {"level": logging_level},
        "rsi_org_name": rsi_org_name,
    }

    if roles is not None:
        config["roles"] = roles
    else:
        config["roles"] = {
            "bot_admins": [],
            "moderators": [],
            "staff": [],
            "verified": "Verified",
            "affiliate": "Affiliate",
            "non_member": "Non-Member",
        }

    if channels is not None:
        config["channels"] = channels
    else:
        config["channels"] = {
            "verification": None,
            "leadership_log": None,
        }

    if voice is not None:
        config["voice"] = voice
    else:
        config["voice"] = {
            "enabled": True,
            "default_user_limit": 10,
            "channel_cleanup_delay": 60,
        }

    if verification is not None:
        config["verification"] = verification
    else:
        config["verification"] = {
            "enabled": True,
            "recheck_interval": 86400,
            "token_digits": 4,
        }

    if extra:
        config.update(extra)

    return config


def make_minimal_config() -> dict[str, Any]:
    """
    Create a minimal valid configuration with only required fields.

    Useful for testing defaults and missing key handling.

    Returns:
        Minimal configuration dictionary.
    """
    return {
        "token": "test_token",
    }


def make_invalid_config(
    issue: str = "missing_token",
) -> dict[str, Any]:
    """
    Create an intentionally invalid configuration for error handling tests.

    Args:
        issue: Type of issue to introduce:
            - "missing_token": No token field
            - "invalid_logging_level": Invalid logging level string
            - "wrong_type_prefix": Prefix as non-string/non-list
            - "invalid_yaml": Returns string that's not valid YAML structure

    Returns:
        Invalid configuration dictionary.
    """
    if issue == "missing_token":
        return {"prefix": "!"}

    elif issue == "invalid_logging_level":
        return {
            "token": "test_token",
            "logging": {"level": "SUPER_DEBUG"},  # Invalid level
        }

    elif issue == "wrong_type_prefix":
        return {
            "token": "test_token",
            "prefix": {"not": "a valid prefix"},  # Dict instead of str/list
        }

    else:
        return {"token": "test_token"}


@contextlib.contextmanager
def temp_config_file(
    config: dict[str, Any] | None = None,
    content: str | None = None,
) -> Generator[str, None, None]:
    """
    Create a temporary config file for testing.

    Args:
        config: Configuration dictionary to write as YAML
        content: Raw string content (overrides config dict)

    Yields:
        Path to the temporary config file.

    Examples:
        # With config dict
        with temp_config_file(make_config()) as path:
            loader = ConfigLoader()
            loader.load_config(path)

        # With raw content (for testing parse errors)
        with temp_config_file(content="invalid: yaml: content:") as path:
            loader = ConfigLoader()
            loader.load_config(path)  # Should handle gracefully
    """
    fd, path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if content is not None:
                f.write(content)
            elif config is not None:
                yaml.safe_dump(config, f)
            else:
                yaml.safe_dump(make_config(), f)
        yield path
    finally:
        with contextlib.suppress(Exception):
            Path(path).unlink()


def make_env_overrides(
    token: str | None = None,
    config_path: str | None = None,
    log_level: str | None = None,
) -> dict[str, str]:
    """
    Create environment variable overrides for testing.

    Args:
        token: DISCORD_TOKEN override
        config_path: CONFIG_PATH override
        log_level: LOG_LEVEL override

    Returns:
        Dictionary of environment variables to set.
    """
    env: dict[str, str] = {}
    if token is not None:
        env["DISCORD_TOKEN"] = token
    if config_path is not None:
        env["CONFIG_PATH"] = config_path
    if log_level is not None:
        env["LOG_LEVEL"] = log_level
    return env
