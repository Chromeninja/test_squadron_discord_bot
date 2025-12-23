"""
Log export routes for admin dashboard.
"""

import csv
import io
import json

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    project_root,
    require_bot_admin,
    translate_internal_api_error,
)
from core.schemas import UserProfile
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _create_streaming_response(
    content: bytes | str, filename: str, media_type: str = "text/plain; charset=utf-8"
) -> StreamingResponse:
    """Create a streaming response with download headers."""
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers=headers,
    )


def _read_tail_bytes(file_path, max_bytes: int) -> bytes:
    """Read the last max_bytes from a file, starting at a line boundary."""
    file_size = file_path.stat().st_size
    start_pos = max(0, file_size - max_bytes)

    with open(file_path, "rb") as f:
        f.seek(start_pos)
        content = f.read(max_bytes)

    # If we started mid-file, skip to the next newline to avoid partial lines
    if start_pos > 0:
        first_newline = content.find(b"\n")
        if first_newline != -1:
            content = content[first_newline + 1 :]

    return content


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

    return _create_streaming_response(content, "bot.log.tail.txt")


@router.get("/backend-export", dependencies=[Depends(require_bot_admin())])
async def export_backend_logs(
    max_bytes: int = Query(default=1048576, ge=1, le=20971520),
):
    """
    Export recent backend logs as plain text (admin only).

    Query params:
    - max_bytes: max bytes to fetch (default 1MB, capped at 20MB)
    """
    backend_log_path = project_root() / "web" / "backend" / "logs" / "bot.log"

    if not backend_log_path.exists():
        raise HTTPException(status_code=404, detail="Backend log file not found")

    try:
        content = _read_tail_bytes(backend_log_path, max_bytes)
        return _create_streaming_response(content, "backend.log.tail.txt")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to export backend logs")
        raise HTTPException(
            status_code=500, detail=f"Failed to export backend logs: {e}"
        ) from e


@router.get("/audit-export", dependencies=[Depends(require_bot_admin())])
async def export_audit_logs(
    limit: int = Query(default=1000, ge=1, le=10000),
    current_user: UserProfile = Depends(require_bot_admin()),
):
    """
    Export audit logs as CSV (admin only).

    Query params:
    - limit: maximum number of audit log entries to export (default 1000, max 10000)
    """
    guild_id = current_user.active_guild_id

    if not guild_id:
        raise HTTPException(status_code=400, detail="No active guild selected")

    try:
        audit_logs = await Database.fetch_audit_logs_by_guild(str(guild_id), limit=limit)

        # Create CSV in memory
        output = io.StringIO()
        fieldnames = [
            "timestamp",
            "admin_user_id",
            "action",
            "target_user_id",
            "details",
            "status",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for log in audit_logs:
            row = log.copy()
            # Compact JSON details for CSV readability
            if row.get("details"):
                try:
                    details_obj = json.loads(row["details"])
                    row["details"] = json.dumps(details_obj, separators=(",", ":"))
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep as-is if not valid JSON
            writer.writerow(row)

        csv_content = output.getvalue()
        output.close()

        return _create_streaming_response(
            csv_content,
            f"audit_log_{guild_id}.csv",
            media_type="text/csv; charset=utf-8",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to export audit logs")
        raise HTTPException(
            status_code=500, detail=f"Failed to export audit logs: {e}"
        ) from e
