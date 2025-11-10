"""
Error monitoring routes for admin dashboard.

Provides endpoints for viewing recent error logs.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from core.dependencies import get_internal_api_client, require_any, InternalAPIClient
from core.schemas import ErrorsResponse, StructuredError

router = APIRouter(prefix="/api/errors", tags=["errors"])


@router.get("/last", response_model=ErrorsResponse, dependencies=[Depends(require_any("admin"))])
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
        
        # Transform to structured error objects
        errors = [StructuredError(**error) for error in result.get("errors", [])]
        
        return ErrorsResponse(errors=errors)
        
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch error logs: {str(e)}"
        )
