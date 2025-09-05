"""Typed configuration package for the Discord bot application."""

from .schema import AppConfig
from .loader import load_config, ConfigValidationError

__all__ = ["AppConfig", "load_config", "ConfigValidationError"]
