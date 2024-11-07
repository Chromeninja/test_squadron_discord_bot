# config/config_loader.py

import yaml
import logging
import os
from typing import Any, Dict

class ConfigLoader:
    _config: Dict[str, Any] = {}

    @classmethod
    def load_config(cls, config_path: str = "config/config.yaml") -> Dict[str, Any]:
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
        return cls._config.get(key, default)
