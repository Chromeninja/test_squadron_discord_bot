"""
Error monitoring routes for admin dashboard.

Provides endpoints for viewing recent error logs.
"""

import logging

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_bot_admin,
    translate_internal_api_error,
)
from core.schemas import ErrorsResponse, StructuredError
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/api/errors", tags=["errors"])
logger = logging.getLogger(__name__)


@router.get(
    "/last", response_model=ErrorsResponse, dependencies=[Depends(require_bot_admin())]
)
async def get_last_errors(
    limit: int = Query(default=1, ge=1, le=100),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get most recent error log entries (admin only).

    Reads from structured error logs and returns the most recent errors.

    Query params:
    - limit: Number of errors to return (1-100, default 1)

    Requires: Admin role
    """
    try:
        result = await internal_api.get_last_errors(limit=limit)

        # Transform to structured error objects, mapping legacy keys
        transformed: list[StructuredError] = []
        for error in result.get("errors", []):
            if not isinstance(error, dict):
                continue
            payload = {
                "time": error.get("time"),
                # Map internal log keys to schema
                "error_type": error.get("error_type") or error.get("level"),
                "component": error.get("component") or error.get("module"),
                "message": error.get("message"),
                "traceback": error.get("traceback"),
            }
            try:
                transformed.append(StructuredError(**payload))
            except Exception as parse_exc:
                # Skip entries that don't conform (e.g., missing required fields)
                logger.debug(
                    "Skipping malformed error entry", exc_info=parse_exc
                )
                continue

        errors = transformed

        return ErrorsResponse(errors=errors)

    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to fetch error logs")
