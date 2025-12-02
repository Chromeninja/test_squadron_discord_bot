# Config/config_loader.py

import logging
from pathlib import Path
from typing import Any, ClassVar

import yaml


class ConfigLoader:
    """
    Singleton class to load and provide access to configuration data.
    """

    _config: ClassVar[dict[str, Any]] = {}

    @classmethod
    def load_config(cls, config_path: str = "config/config.yaml") -> dict[str, Any]:
        """Load the configuration from a YAML file if not already loaded.

        Args:
            config_path: Path to the configuration file. Defaults to
                ``config/config.yaml``.

        Returns:
            Dict[str, Any]: Loaded configuration dictionary.
        """
        if not cls._config:
            try:
                with Path(config_path).open(encoding="utf-8") as file:
                    cls._config = yaml.safe_load(file) or {}
                logging.info("Configuration loaded successfully.")

                # Ensure we have a dict to operate on
                if not isinstance(cls._config, dict):
                    logging.warning(
                        "Configuration file didn't contain a mapping; "
                        "using empty config."
                    )
                    cls._config = {}

                # Convert role IDs to integers
                cls._convert_role_ids_to_int()

                # Validate logging level
                cls._validate_logging_level()

            except FileNotFoundError:
                logging.warning(
                    "Configuration file not found at path: %s; "
                    "using empty/default config.",
                    config_path,
                )
                cls._config = {}
            except yaml.YAMLError:
                logging.exception(
                    "Error parsing configuration; using empty/default config."
                )
                cls._config = {}
            except UnicodeDecodeError:
                logging.exception(
                    "Encoding error reading configuration; using empty/default config."
                )
                cls._config = {}
        return cls._config

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
    def _convert_role_ids_to_int(cls) -> None:
        """
        Convert role IDs in config to integers (DEPRECATED - roles now managed in database).

        Kept for backward compatibility but no longer processes roles section.
        """
        # Roles are now managed per-guild in the database
        # This method is kept as a no-op for backward compatibility
        pass

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
