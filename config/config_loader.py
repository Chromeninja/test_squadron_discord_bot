# config/config_loader.py

import yaml
import logging
import os
from typing import Any, Dict

class ConfigLoader:
    """
    Singleton class to load and provide access to configuration data.
    """
    _config: Dict[str, Any] = {}

    @classmethod
    def load_config(cls, config_path: str = "config/config.yaml") -> Dict[str, Any]:
        """
        Loads the configuration from a YAML file if not already loaded.

        Args:
            config_path (str, optional): Path to the configuration file. Defaults to "config/config.yaml".

        Returns:
            Dict[str, Any]: Loaded configuration dictionary.
        """
        if not cls._config:
            try:
                with open(config_path, 'r') as file:
                    cls._config = yaml.safe_load(file)
                logging.info("Configuration loaded successfully.")
            except FileNotFoundError:
                logging.error(f"Configuration file not found at path: {config_path}")
                raise
            except yaml.YAMLError as e:
                logging.error(f"Error parsing the configuration file: {e}")
                raise
        return cls._config

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from the configuration.

        Args:
            key (str): The key to retrieve from the configuration.
            default (Any, optional): Default value if the key is not found. Defaults to None.

        Returns:
            Any: The value associated with the key or the default.
        """
        return cls._config.get(key, default)
