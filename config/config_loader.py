# Config/config_loader.py

import logging
from typing import Any

import yaml


class ConfigLoader:
    """
    Singleton class to load and provide access to configuration data.
    """

    _config: dict[str, Any] = {}

    @classmethod
    def load_config(cls, config_path: str = "config/config.yaml") -> dict[str, Any]:
        """
        Loads the configuration from a YAML file if not already loaded.

        Args:
            config_path (str, optional): Path to the configuration file. Defaults to "config/config.yaml".

        Returns:
            Dict[str, Any]: Loaded configuration dictionary.
        """
        if not cls._config:
            try:
                with open(config_path, encoding="utf-8") as file:
                    cls._config = yaml.safe_load(file) or {}
                logging.info("Configuration loaded successfully.")

                # Ensure we have a dict to operate on
                if not isinstance(cls._config, dict):
                    logging.warning(
                        "Configuration file did not contain a mapping; using empty config."
                    )
                    cls._config = {}

                # Convert role IDs to integers
                cls._convert_role_ids_to_int()

                # Validate logging level
                cls._validate_logging_level()

            except FileNotFoundError:
                logging.warning(
                    f"Configuration file not found at path: {config_path}; using empty/default config."
                )
                cls._config = {}
            except yaml.YAMLError as e:
                logging.exception(
                    f"Error parsing the configuration file: {e}; using empty/default config."
                )
                cls._config = {}
            except UnicodeDecodeError as e:
                logging.exception(
                    f"Encoding error while reading the configuration file: {e}; using empty/default config."
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
            cls._config["logging"]["level"] = "INFO"

    @classmethod
    def _convert_role_ids_to_int(cls) -> None:
        """
        Converts all role IDs in the configuration from strings to integers.
        """
        roles = cls._config.get("roles", {})

        # Define keys that should be single role IDs
        single_role_keys = [
            "bot_verified_role_id",
            "main_role_id",
            "affiliate_role_id",
            "non_member_role_id",
        ]

        for key in single_role_keys:
            if key in roles:
                try:
                    roles[key] = int(roles[key])
                    logging.debug(f"Converted {key} to integer: {roles[key]}")
                except ValueError:
                    logging.exception(f"Role ID for {key} must be an integer.")
                    raise

                    # Define keys that are lists of role IDs
        list_role_keys = ["bot_admins", "lead_moderators"]

        for key in list_role_keys:
            if key in roles:
                try:
                    roles[key] = [int(role_id) for role_id in roles[key]]
                    logging.debug(f"Converted {key} to list of integers: {roles[key]}")
                except ValueError:
                    logging.exception(f"All role IDs in {key} must be integers.")
                    raise

                    # Convert selectable_roles from config to a list of integers if present
        if "selectable_roles" in cls._config:
            try:
                cls._config["selectable_roles"] = [
                    int(role_id) for role_id in cls._config["selectable_roles"]
                ]
                logging.debug(
                    f"Converted selectable_roles to list of integers: {cls._config['selectable_roles']}"
                )
            except ValueError:
                logging.exception("All selectable_roles must be integers.")
                raise

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from the configuration.

        Args:
            key (str): The key to retrieve.
            default (Any, optional): The default value if key is not found. Defaults to None.

        Returns:
            Any: The value associated with the key.
        """
        return cls._config.get(key, default)
