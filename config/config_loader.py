# Config/config_loader.py

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

import yaml


def _get_project_root() -> Path:
    """Derive project root from this file's location: config/config_loader.py -> project root."""
    return Path(__file__).resolve().parent.parent


class ConfigLoader:
    """
    Singleton class to load and provide access to configuration data.

    Observability:
        - Logs INFO on successful config load with path
        - Logs WARNING on missing config file (degraded mode)
        - Logs ERROR on YAML parse errors
        - Tracks config_status for health reporting
    """

    _config: ClassVar[dict[str, Any]] = {}
    _config_status: ClassVar[str] = "not_loaded"  # "ok", "degraded", "error"
    _config_path: ClassVar[str | None] = None

    @classmethod
    def load_config(cls, config_path: str | None = None) -> dict[str, Any]:
        """Load the configuration from a YAML file if not already loaded.

        Args:
            config_path: Path to the configuration file. If not provided,
                uses CONFIG_PATH env var or defaults to project_root/config/config.yaml.

        Returns:
            Dict[str, Any]: Loaded configuration dictionary.

        Observability:
            - Logs INFO with resolved path on successful load
            - Logs WARNING if file missing (degraded mode continues)
            - Logs ERROR if YAML invalid
        """
        if not cls._config:
            # Resolve config path with priority: explicit arg > env var > default
            if config_path is None:
                config_path = os.environ.get("CONFIG_PATH")
                if config_path:
                    logging.info(
                        "Config path overridden via CONFIG_PATH env: %s", config_path
                    )

            if config_path is None:
                config_path = str(_get_project_root() / "config" / "config.yaml")

            cls._config_path = config_path

            try:
                with Path(config_path).open(encoding="utf-8") as file:
                    cls._config = yaml.safe_load(file) or {}

                # Ensure we have a dict to operate on
                if not isinstance(cls._config, dict):
                    logging.warning(
                        "Configuration file didn't contain a mapping; "
                        "using empty config."
                    )
                    cls._config = {}
                    cls._config_status = "degraded"
                else:
                    cls._config_status = "ok"
                    logging.info(
                        "Configuration loaded successfully from %s", config_path
                    )

                # Validate logging level
                cls._validate_logging_level()

            except FileNotFoundError:
                logging.warning(
                    "Configuration file not found at path: %s; "
                    "using empty/default config (degraded mode).",
                    config_path,
                )
                cls._config = {}
                cls._config_status = "degraded"
            except yaml.YAMLError as e:
                logging.error(
                    "Error parsing configuration YAML at %s: %s; "
                    "using empty/default config.",
                    config_path,
                    e,
                )
                cls._config = {}
                cls._config_status = "error"
            except UnicodeDecodeError as e:
                logging.error(
                    "Encoding error reading configuration at %s: %s; "
                    "using empty/default config.",
                    config_path,
                    e,
                )
                cls._config = {}
                cls._config_status = "error"
        return cls._config

    @classmethod
    def get_config_status(cls) -> dict[str, Any]:
        """Return config health status for observability endpoints.

        Returns:
            Dict with config_status, config_path, and whether config is loaded.
        """
        return {
            "config_status": cls._config_status,
            "config_path": cls._config_path,
            "config_loaded": bool(cls._config),
        }

    @classmethod
    def _validate_logging_level(cls) -> None:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        logging_config = cls._config.get("logging", {})
        level = logging_config.get("level", "INFO").upper()
        if level not in valid_levels:
            logging.warning(
                f"Invalid logging level '{level}' in config. Defaulting to 'INFO'."
            )
            logging_cfg = cls._config.setdefault("logging", {})
            logging_cfg["level"] = "INFO"

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from the configuration.

        Args:
            key (str): The key to retrieve.
            default (Any, optional): The default value if the key is not found.
                Defaults to None.

        Returns:
            Any: The value associated with the key.
        """
        return cls._config.get(key, default)

    @classmethod
    def reset(cls) -> None:
        """Reset the config loader state (useful for testing)."""
        cls._config = {}
        cls._config_status = "not_loaded"
        cls._config_path = None


# ---------------------------------------------------------------------------
# Prefix Normalization (Observability-instrumented)
# ---------------------------------------------------------------------------

# Constraints for prefix validation
MAX_PREFIX_LENGTH = 10
MAX_PREFIX_COUNT = 5
ALLOWED_PREFIX_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+[]{}|;:',.<>?/~"
)


def normalize_prefix(
    raw_prefix: Any,
    *,
    mode: str = "enforce",
) -> tuple[list[str], list[str]]:
    """
    Normalize command prefix configuration to a safe, validated list.

    Args:
        raw_prefix: The raw prefix value from YAML config. Can be None, str, list, or other.
        mode: "enforce" (default) applies normalization, "shadow" only logs what would change.

    Returns:
        Tuple of (normalized_prefixes, warnings).
        - normalized_prefixes: List of valid prefix strings, or empty list for mention-only mode.
        - warnings: List of warning messages for operator visibility.

    Normalization rules:
        - None, empty string, empty list -> [] (mention-only mode)
        - Single string -> [trimmed_string] if valid, else [] with warning
        - List -> [trimmed valid strings], deduped, up to MAX_PREFIX_COUNT
        - Invalid types -> [] with warning
        - Whitespace-only strings -> skipped with warning
        - Strings exceeding MAX_PREFIX_LENGTH -> truncated with warning
        - Non-ASCII characters -> rejected with warning

    Observability:
        - Logs INFO with final normalized prefix list
        - Logs WARNING for each validation issue
    """
    logger = logging.getLogger(__name__)
    warnings: list[str] = []
    normalized: list[str] = []
    seen: set[str] = set()

    def _validate_and_add(prefix: str, source_desc: str) -> None:
        """Validate a single prefix string and add to normalized list if valid."""
        # Trim whitespace
        trimmed = prefix.strip()

        # Skip empty after trim
        if not trimmed:
            msg = f"Whitespace-only prefix from {source_desc} ignored"
            warnings.append(msg)
            logger.warning(msg)
            return

        # Check for non-ASCII characters
        if not trimmed.isascii():
            msg = f"Non-ASCII prefix '{trimmed[:20]}...' from {source_desc} rejected"
            warnings.append(msg)
            logger.warning(msg)
            return

        # Check for disallowed characters (backtick, newline)
        if "`" in trimmed or "\n" in trimmed:
            msg = f"Prefix contains disallowed characters (backtick/newline) from {source_desc}"
            warnings.append(msg)
            logger.warning(msg)
            return

        # Truncate if too long
        if len(trimmed) > MAX_PREFIX_LENGTH:
            msg = f"Prefix '{trimmed[:MAX_PREFIX_LENGTH]}...' exceeds max length {MAX_PREFIX_LENGTH}; truncated"
            warnings.append(msg)
            logger.warning(msg)
            trimmed = trimmed[:MAX_PREFIX_LENGTH]

        # Check prefix count limit
        if len(normalized) >= MAX_PREFIX_COUNT:
            msg = f"Prefix count limit ({MAX_PREFIX_COUNT}) reached; '{trimmed}' ignored"
            warnings.append(msg)
            logger.warning(msg)
            return

        # Dedupe
        if trimmed in seen:
            logger.debug(f"Duplicate prefix '{trimmed}' ignored")
            return

        seen.add(trimmed)
        normalized.append(trimmed)

    # Handle different input types
    if raw_prefix is None:
        logger.info("No prefix configured; bot will respond to mentions only")
        return [], warnings

    if isinstance(raw_prefix, str):
        if not raw_prefix.strip():
            logger.info("Empty string prefix; bot will respond to mentions only")
            return [], warnings
        _validate_and_add(raw_prefix, "string config")

    elif isinstance(raw_prefix, list):
        if not raw_prefix:
            logger.info("Empty list prefix; bot will respond to mentions only")
            return [], warnings

        for i, item in enumerate(raw_prefix):
            if isinstance(item, str):
                _validate_and_add(item, f"list item {i}")
            else:
                msg = f"Non-string item at index {i} (type={type(item).__name__}) in prefix list ignored"
                warnings.append(msg)
                logger.warning(msg)

    else:
        # Invalid type
        msg = f"Invalid prefix type {type(raw_prefix).__name__}; falling back to mention-only"
        warnings.append(msg)
        logger.warning(msg)
        return [], warnings

    # Final logging
    if normalized:
        logger.info(f"Command prefix set to {normalized}")
    else:
        logger.info("No valid prefixes after normalization; bot will respond to mentions only")

    if warnings and mode == "enforce":
        logger.warning(
            f"Prefix normalization completed with {len(warnings)} warning(s)"
        )

    return normalized, warnings
