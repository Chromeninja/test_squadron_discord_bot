"""
Custom exception classes for the Discord bot.

These provide a hierarchy of typed exceptions for better error handling.
"""


class BotError(Exception):
    """Base exception for bot-related errors."""

    pass


class ConfigError(BotError):
    """Exception raised for configuration-related errors."""

    pass


class DatabaseError(BotError):
    """Exception raised for database-related errors."""

    pass


class ServiceError(BotError):
    """Exception raised for service-related errors."""

    pass
