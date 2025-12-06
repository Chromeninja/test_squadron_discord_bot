"""
Log export routes for admin dashboard.
"""

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_bot_admin,
    translate_internal_api_error,
)
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/export", dependencies=[Depends(require_bot_admin())])
async def export_logs(
    max_bytes: int = Query(default=1048576, ge=1, le=20971520),
    lines: int | None = Query(default=None, ge=1, le=100000),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Export recent bot logs as plain text (admin only).

    Query params:
    - max_bytes: max bytes to fetch (default 1MB, capped at 20MB)
    - lines: optional hint for the number of log lines (accepted for compatibility)
    """
    try:
        content = await internal_api.export_logs(max_bytes=max_bytes)
    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to export logs")

    filename = "bot.log.tail.txt"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
    }

    return StreamingResponse(
        iter([content]),
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )
