"""
Log export routes for admin dashboard.

Provides endpoints for downloading bot logs, backend logs, and audit logs.
"""

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

from core.dependencies import (
    InternalAPIClient,
    get_internal_api_client,
    require_bot_admin,
    require_fresh_guild_access,
    translate_internal_api_error,
)
from core.schemas import UserProfile
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from config.config_loader import ConfigLoader
from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/export", dependencies=[Depends(require_bot_admin()), Depends(require_fresh_guild_access)])
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
            headers={"Content-Disposition": "attachment; filename=bot.log.tail.txt"},
        )

    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to export logs")


@router.get("/backend-export", dependencies=[Depends(require_bot_admin()), Depends(require_fresh_guild_access)])
async def export_backend_logs(
    max_bytes: int = Query(default=1048576, ge=1024, le=5242880),
):
    """
    Export backend API logs as downloadable file (admin only).

    Returns the tail of the backend log file.

    Query params:
    - max_bytes: Maximum bytes to read (1KB-5MB, default 1MB)

    Requires: Admin role
    """
    try:
        # Get backend log file path
        backend_log_file = Path(__file__).parent.parent / "logs" / "bot.log"

        if not backend_log_file.exists():
            return StreamingResponse(
                io.BytesIO(b"Backend log file not found"),
                media_type="text/plain",
                headers={
                    "Content-Disposition": "attachment; filename=backend.log.tail.txt"
                },
            )

        # Read tail of file efficiently
        file_size = backend_log_file.stat().st_size

        if file_size <= max_bytes:
            # File is smaller than limit, read entire file
            with open(backend_log_file, "rb") as f:
                content = f.read()
        else:
            # Read last N bytes
            with open(backend_log_file, "rb") as f:
                f.seek(-max_bytes, 2)  # Seek to N bytes before end
                content = f.read()

                # Try to start at a newline to avoid partial line
                first_newline = content.find(b"\n")
                if first_newline != -1 and first_newline < 1000:
                    content = content[first_newline + 1 :]

        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=backend.log.tail.txt"
            },
        )

    except Exception as e:
        logger.exception("Error exporting backend logs", exc_info=e)
        raise translate_internal_api_error(e, "Failed to export backend logs")


@router.get("/audit-export", dependencies=[Depends(require_bot_admin()), Depends(require_fresh_guild_access)])
async def export_audit_logs(
    current_user: UserProfile = Depends(require_bot_admin()),
    limit: int = Query(default=1000, ge=1, le=10000),
):
    """
    Export guild-specific audit logs as CSV file (admin only).

    Returns audit log entries for the user's active guild in CSV format.

    Query params:
    - limit: Maximum number of rows to return (1-10000, default 1000)

    Requires: Admin role
    """
    try:
        # Load config to get max rows limit
        config = ConfigLoader.load_config()
        max_rows = config.get("log_retention", {}).get("audit_export_max_rows", 10000)
        limit = min(limit, max_rows)

        guild_id = str(current_user.active_guild_id)

        # Fetch audit logs from database
        logs = await Database.fetch_audit_logs_by_guild(guild_id, limit=limit)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "Timestamp",
                "Admin_User_ID",
                "Action",
                "Target_User_ID",
                "Status",
                "Details",
            ]
        )

        # Write data rows
        for log in logs:
            # Format timestamp as readable datetime
            timestamp_str = datetime.fromtimestamp(log["timestamp"], UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )

            writer.writerow(
                [
                    timestamp_str,
                    log["admin_user_id"] or "",
                    log["action"] or "",
                    log["target_user_id"] or "",
                    log["status"] or "",
                    log["details"] or "",
                ]
            )

        # Get CSV content and convert to bytes
        csv_content = output.getvalue()
        output.close()

        # Generate filename with guild ID and date
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        filename = f"audit_log_guild_{guild_id}_{date_str}.csv"

        # Return as downloadable CSV file
        return StreamingResponse(
            io.BytesIO(csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.exception("Error exporting audit logs", exc_info=e)
        raise translate_internal_api_error(e, "Failed to export audit logs")
