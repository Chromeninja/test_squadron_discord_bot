"""
Utilities for building structured logging context for backend API requests.

Provides helper functions to extract endpoint, method, user info from FastAPI requests.
"""

from typing import Any

from fastapi import Request

from web.backend.core.request_id import get_request_id


def get_api_log_extra(
    request: Request | None = None,
    endpoint: str | None = None,
    method: str | None = None,
    user_id: str | None = None,
    guild_id: str | None = None,
    **additional: Any,
) -> dict[str, Any]:
    """
    Build a structured logging extra dict for API requests.

    Args:
        request: FastAPI Request object (extracts endpoint, method if not provided)
        endpoint: API endpoint path (overrides request.url.path if provided)
        method: HTTP method (overrides request.method if provided)
        user_id: Discord user ID
        guild_id: Discord guild ID
        **additional: Any additional key-value pairs to include

    Returns:
        Dict with request_id, endpoint, method, user_id, guild_id, and additional fields

    Examples:
        # From request object
        logger.info("API request received", extra=get_api_log_extra(request))

        # With additional context
        logger.info("User lookup", extra=get_api_log_extra(request, user_id=str(user_id)))

        # Manual composition
        logger.info("Background task", extra=get_api_log_extra(
            endpoint="/api/cleanup",
            method="TASK",
            task_type="log_cleanup"
        ))
    """
    extra: dict[str, Any] = {}

    # Add request ID from context
    request_id = get_request_id()
    if request_id:
        extra["request_id"] = request_id

    # Extract from request if provided
    if request:
        if not endpoint:
            endpoint = request.url.path
        if not method:
            method = request.method

    # Add fields
    if endpoint:
        extra["endpoint"] = endpoint
    if method:
        extra["method"] = method
    if user_id:
        extra["user_id"] = str(user_id)
    if guild_id:
        extra["guild_id"] = str(guild_id)

    # Merge any additional fields
    extra.update(additional)

    return extra
