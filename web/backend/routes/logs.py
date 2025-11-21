"""
Log export routes for admin dashboard.

Provides endpoints for downloading bot logs.
"""

import io

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_any,
    translate_internal_api_error,
)
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/export", dependencies=[Depends(require_any("admin"))])
async def export_logs(
    max_bytes: int = Query(default=1048576, ge=1024, le=5242880),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Export bot logs as downloadable file (admin only).
    
    Returns the tail of the main bot log file.
    
    Query params:
    - max_bytes: Maximum bytes to read (1KB-5MB, default 1MB)
    
    Requires: Admin role
    """
    try:
        content = await internal_api.export_logs(max_bytes=max_bytes)

        # Create a streaming response with proper headers for download
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=bot.log.tail.txt"
            }
        )

    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to export logs")
