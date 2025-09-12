"""
Database Package

Database access layer for the Discord bot.
"""

from .database import Database
from .schema import init_schema

__all__ = ["Database", "init_schema"]
