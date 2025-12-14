"""
Base Repository Pattern for Database Access.

Provides a unified interface for database operations, eliminating
repetitive connection/cursor patterns throughout the codebase.

Usage:
    class UserRepository(BaseRepository):
        async def get_user(self, user_id: int) -> dict | None:
            return await self.fetch_one(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            )
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from .database import Database

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aiosqlite import Row

T = TypeVar("T")


class BaseRepository:
    """
    Base class for repository pattern database access.

    Provides common query methods that handle connection management,
    cursor operations, and result processing uniformly.
    """

    @staticmethod
    @asynccontextmanager
    async def transaction():
        """
        Context manager for explicit transaction control.

        Usage:
            async with BaseRepository.transaction() as db:
                await db.execute("INSERT ...", params)
                await db.execute("UPDATE ...", params)
                # Auto-commits on success, rolls back on exception
        """
        async with Database.get_connection() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    @staticmethod
    @asynccontextmanager
    async def exclusive_transaction():
        """
        Context manager for exclusive transaction control.

        Uses BEGIN EXCLUSIVE to prevent other connections from writing
        during the transaction, providing stronger isolation for
        critical operations like preventing TOCTOU race conditions.

        Usage:
            async with BaseRepository.exclusive_transaction() as db:
                await db.execute("SELECT ...", params)
                await db.execute("INSERT ...", params)
                # Auto-commits on success, rolls back on exception
        """
        async with Database.get_connection() as db:
            await db.execute("BEGIN EXCLUSIVE TRANSACTION")
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    @staticmethod
    async def fetch_one(
        query: str,
        params: tuple[Any, ...] = (),
    ) -> Row | None:
        """
        Execute a query and return a single row.

        Args:
            query: SQL query string with ? placeholders
            params: Query parameters

        Returns:
            Single row or None if not found
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchone()

    @staticmethod
    async def fetch_all(
        query: str,
        params: tuple[Any, ...] = (),
    ) -> list[Row]:
        """
        Execute a query and return all rows.

        Args:
            query: SQL query string with ? placeholders
            params: Query parameters

        Returns:
            List of rows (empty list if none found)
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(query, params)
            return list(await cursor.fetchall())

    @staticmethod
    async def fetch_value(
        query: str,
        params: tuple[Any, ...] = (),
        default: T = None,
    ) -> T | Any:
        """
        Execute a query and return a single value from the first column.

        Args:
            query: SQL query string with ? placeholders
            params: Query parameters
            default: Default value if no row found

        Returns:
            First column value or default
        """
        row = await BaseRepository.fetch_one(query, params)
        return row[0] if row else default

    @staticmethod
    async def execute(
        query: str,
        params: tuple[Any, ...] = (),
        commit: bool = True,
    ) -> int:
        """
        Execute a write query (INSERT, UPDATE, DELETE).

        Args:
            query: SQL query string with ? placeholders
            params: Query parameters
            commit: Whether to auto-commit (default: True)

        Returns:
            Number of rows affected
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(query, params)
            if commit:
                await db.commit()
            return cursor.rowcount

    @staticmethod
    async def execute_many(
        query: str,
        params_list: Sequence[tuple[Any, ...]],
        commit: bool = True,
    ) -> int:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query string with ? placeholders
            params_list: List of parameter tuples
            commit: Whether to auto-commit (default: True)

        Returns:
            Total rows affected
        """
        async with Database.get_connection() as db:
            await db.executemany(query, params_list)
            if commit:
                await db.commit()
            return len(params_list)

    @staticmethod
    async def exists(
        query: str,
        params: tuple[Any, ...] = (),
    ) -> bool:
        """
        Check if any rows match the query.

        Args:
            query: SQL query (typically SELECT 1 FROM ... WHERE ...)
            params: Query parameters

        Returns:
            True if at least one row exists
        """
        row = await BaseRepository.fetch_one(query, params)
        return row is not None

    @staticmethod
    async def insert_returning_id(
        query: str,
        params: tuple[Any, ...] = (),
    ) -> int | None:
        """
        Execute an INSERT and return the last inserted row ID.

        Args:
            query: INSERT query string
            params: Query parameters

        Returns:
            Last inserted row ID or None
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.lastrowid


# -----------------------------------------------------------------------------
# JSON Parsing Utilities
# -----------------------------------------------------------------------------


def parse_json_list(value: str | None, default: list | None = None) -> list:
    """
    Safely parse a JSON string into a list.

    Args:
        value: JSON string or None
        default: Default value if parsing fails (default: empty list)

    Returns:
        Parsed list or default
    """
    if default is None:
        default = []
    if not value:
        return default
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else default
    except (json.JSONDecodeError, TypeError):
        return default


def parse_json_dict(value: str | None, default: dict | None = None) -> dict:
    """
    Safely parse a JSON string into a dict.

    Args:
        value: JSON string or None
        default: Default value if parsing fails (default: empty dict)

    Returns:
        Parsed dict or default
    """
    if default is None:
        default = {}
    if not value:
        return default
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else default
    except (json.JSONDecodeError, TypeError):
        return default


def encode_json(value: Any) -> str:
    """
    Encode a value as a JSON string.

    Args:
        value: Value to encode

    Returns:
        JSON string
    """
    return json.dumps(value)


# -----------------------------------------------------------------------------
# Snowflake ID Utilities
# -----------------------------------------------------------------------------


def parse_snowflake(value: Any) -> int | None:
    """
    Parse a Discord snowflake ID from various input types.

    Handles strings, ints, and None gracefully.

    Args:
        value: Raw ID value (str, int, or None)

    Returns:
        Integer ID or None if invalid
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_snowflake_strict(value: Any, name: str = "ID") -> int:
    """
    Parse a Discord snowflake ID, raising ValueError if invalid.

    Args:
        value: Raw ID value
        name: Name of the field for error message

    Returns:
        Integer ID

    Raises:
        ValueError: If the value cannot be parsed
    """
    result = parse_snowflake(value)
    if result is None:
        raise ValueError(f"Invalid {name} format: {value!r}")
    return result


# -----------------------------------------------------------------------------
# Organization Data Utilities
# -----------------------------------------------------------------------------


def derive_membership_status(
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    target_sid: str = "TEST",
) -> str:
    """
    Derive membership status from organization SID lists.

    Checks if the target organization SID appears in the user's main or affiliate
    organization lists and returns the appropriate status.

    Args:
        main_orgs: List of main organization SIDs
        affiliate_orgs: List of affiliate organization SIDs
        target_sid: Organization SID to check for (defaults to "TEST")

    Returns:
        str: One of "main", "affiliate", or "non_member"
    """
    if not main_orgs:
        main_orgs = []
    if not affiliate_orgs:
        affiliate_orgs = []

    # Normalize to uppercase for comparison
    target_upper = target_sid.upper()
    main_upper = [sid.upper() for sid in main_orgs if sid and sid != "REDACTED"]
    affiliate_upper = [
        sid.upper() for sid in affiliate_orgs if sid and sid != "REDACTED"
    ]

    if target_upper in main_upper:
        return "main"
    if target_upper in affiliate_upper:
        return "affiliate"
    return "non_member"


def parse_org_lists(
    main_orgs_json: str | None,
    affiliate_orgs_json: str | None,
) -> tuple[list[str], list[str]]:
    """
    Parse main and affiliate organization JSON strings.

    Args:
        main_orgs_json: JSON string of main orgs
        affiliate_orgs_json: JSON string of affiliate orgs

    Returns:
        Tuple of (main_orgs, affiliate_orgs) lists
    """
    main_orgs = parse_json_list(main_orgs_json)
    affiliate_orgs = parse_json_list(affiliate_orgs_json)
    return main_orgs, affiliate_orgs


# -----------------------------------------------------------------------------
# Export common repository instance
# -----------------------------------------------------------------------------


# Singleton repository instance for convenience
repo = BaseRepository()


__all__ = [
    "BaseRepository",
    "derive_membership_status",
    "encode_json",
    "parse_json_dict",
    "parse_json_list",
    "parse_org_lists",
    "parse_snowflake",
    "parse_snowflake_strict",
    "repo",
]
