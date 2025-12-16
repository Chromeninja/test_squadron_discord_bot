"""
Web Backend Validation Utilities.

Provides reusable validation functions and decorators for FastAPI routes,
eliminating duplicated HTTPException patterns and ID parsing logic.
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

if TYPE_CHECKING:
    from core.schemas import UserProfile


# -----------------------------------------------------------------------------
# ID Parsing Utilities
# -----------------------------------------------------------------------------


def parse_snowflake_id(value: Any, name: str = "ID") -> int:
    """
    Parse a Discord snowflake ID from string/int to integer.

    Args:
        value: Raw ID value (string, int, or None)
        name: Field name for error messages

    Returns:
        Integer ID

    Raises:
        HTTPException: 400 if the ID format is invalid
    """
    if value is None:
        raise HTTPException(status_code=400, detail=f"{name} is required")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {name} format")


def parse_snowflake_id_optional(value: Any) -> int | None:
    """
    Parse a Discord snowflake ID, returning None for invalid values.

    Args:
        value: Raw ID value (string, int, or None)

    Returns:
        Integer ID or None
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# Active Guild Validation
# -----------------------------------------------------------------------------


def ensure_active_guild(current_user: UserProfile) -> int:
    """
    Ensure the user has an active guild selected.

    Args:
        current_user: Current authenticated user profile

    Returns:
        Active guild ID as integer

    Raises:
        HTTPException: 400 if no active guild is selected
    """
    if not current_user.active_guild_id:
        raise HTTPException(status_code=400, detail="No active guild selected")
    return parse_snowflake_id(current_user.active_guild_id, "Guild ID")


def ensure_guild_match(guild_id: int | str, current_user: UserProfile) -> int:
    """
    Ensure the requested guild matches the user's active guild.

    Args:
        guild_id: Requested guild ID
        current_user: Current authenticated user profile

    Returns:
        Validated guild ID as integer

    Raises:
        HTTPException: 400 if no active guild selected
        HTTPException: 403 if guild doesn't match active guild
    """
    active_guild_id = ensure_active_guild(current_user)
    requested_guild_id = parse_snowflake_id(guild_id, "Guild ID")

    if requested_guild_id != active_guild_id:
        raise HTTPException(status_code=403, detail="Active guild mismatch")

    return active_guild_id


def ensure_user_and_guild_ids(
    user_id: Any,
    current_user: UserProfile,
) -> tuple[int, int]:
    """
    Parse and validate user ID and ensure active guild.

    Common pattern for user-specific endpoints.

    Args:
        user_id: User ID from path/query parameter
        current_user: Current authenticated user

    Returns:
        Tuple of (user_id_int, guild_id_int)

    Raises:
        HTTPException: 400 if IDs are invalid or no active guild
    """
    user_id_int = parse_snowflake_id(user_id, "User ID")
    guild_id_int = ensure_active_guild(current_user)
    return user_id_int, guild_id_int


# -----------------------------------------------------------------------------
# Error Translation Utilities
# -----------------------------------------------------------------------------


class APIError(Exception):
    """Base exception for API-related errors with HTTP status code."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or message


def translate_exception_to_http(
    exc: Exception,
    default_message: str = "An error occurred",
    default_status: int = 500,
) -> HTTPException:
    """
    Translate an exception to an HTTPException with appropriate status.

    Args:
        exc: Original exception
        default_message: Default error message prefix
        default_status: Default HTTP status code

    Returns:
        HTTPException with appropriate status and detail
    """
    if isinstance(exc, HTTPException):
        return exc

    if isinstance(exc, APIError):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)

    # Check for common exception patterns
    exc_str = str(exc).lower()

    if "not found" in exc_str:
        return HTTPException(status_code=404, detail=f"{default_message}: Not found")

    if "permission" in exc_str or "forbidden" in exc_str or "unauthorized" in exc_str:
        return HTTPException(
            status_code=403, detail=f"{default_message}: Access denied"
        )

    if "timeout" in exc_str:
        return HTTPException(
            status_code=504, detail=f"{default_message}: Request timeout"
        )

    if "connection" in exc_str:
        return HTTPException(
            status_code=503, detail=f"{default_message}: Service unavailable"
        )

    return HTTPException(status_code=default_status, detail=f"{default_message}: {exc}")


def api_error_handler(default_message: str = "Operation failed"):
    """
    Decorator for handling API errors with consistent translation.

    Args:
        default_message: Default error message for unhandled exceptions

    Returns:
        Decorated function

    Usage:
        @api_error_handler("Failed to fetch user")
        async def get_user(user_id: int):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as exc:
                raise translate_exception_to_http(exc, default_message)

        return wrapper

    return decorator


# -----------------------------------------------------------------------------
# Data Coercion Utilities
# -----------------------------------------------------------------------------


def safe_int(value: Any) -> int | None:
    """
    Safely convert a value to integer.

    Args:
        value: Value to convert

    Returns:
        Integer or None if conversion fails
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_str(value: Any, default: str = "") -> str:
    """
    Safely convert a value to string.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        String representation or default
    """
    if value is None:
        return default
    return str(value)


def coerce_role_list(value: Any) -> list[str]:
    """
    Coerce a role list to a list of string IDs.

    Handles various input formats and deduplicates.

    Args:
        value: Raw role list (list, str, or None)

    Returns:
        List of string role IDs
    """
    if not value:
        return []

    if isinstance(value, str):
        # Handle comma-separated string
        value = [v.strip() for v in value.split(",") if v.strip()]

    if not isinstance(value, list):
        return []

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []

    for item in value:
        item_str = str(item).strip()
        if item_str and item_str not in seen:
            # Validate it's a valid snowflake-like ID
            if safe_int(item_str) is not None:
                seen.add(item_str)
                result.append(item_str)

    return result


def coerce_role_list_int(value: Any) -> list[int]:
    """
    Coerce a role list to a list of integer IDs.

    Args:
        value: Raw role list

    Returns:
        List of integer role IDs
    """
    str_list = coerce_role_list(value)
    return [int(v) for v in str_list]


# -----------------------------------------------------------------------------
# Pagination Utilities
# -----------------------------------------------------------------------------


def validate_pagination(
    page: int = 1,
    per_page: int = 50,
    max_per_page: int = 100,
) -> tuple[int, int, int]:
    """
    Validate and normalize pagination parameters.

    Args:
        page: Page number (1-indexed)
        per_page: Items per page
        max_per_page: Maximum allowed items per page

    Returns:
        Tuple of (page, per_page, offset)

    Raises:
        HTTPException: 400 if parameters are invalid
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")

    if per_page < 1:
        raise HTTPException(status_code=400, detail="per_page must be >= 1")

    per_page = min(per_page, max_per_page)

    offset = (page - 1) * per_page
    return page, per_page, offset


__all__ = [
    "APIError",
    "api_error_handler",
    "coerce_role_list",
    "coerce_role_list_int",
    "ensure_active_guild",
    "ensure_guild_match",
    "ensure_user_and_guild_ids",
    "parse_snowflake_id",
    "parse_snowflake_id_optional",
    "safe_int",
    "safe_str",
    "translate_exception_to_http",
    "validate_pagination",
]
