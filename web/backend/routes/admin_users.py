"""
Admin endpoints for user management (recheck, reset timers).
"""

import base64
import time

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_moderator,
)
from core.schemas import UserProfile
from core.validation import (
    ensure_active_guild,
    ensure_user_and_guild_ids,
    parse_snowflake_id,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from helpers.audit import log_admin_action
from helpers.bulk_check import StatusRow, write_csv
from services.db.database import derive_membership_status
from utils.logging import get_logger

logger = get_logger(__name__)

# Maximum number of users that can be rechecked in a single bulk operation
MAX_BULK_RECHECK = 100

router = APIRouter()


class RecheckUserResponse(BaseModel):
    """Response for user recheck operation."""

    success: bool
    message: str
    rsi_handle: str | None = None
    old_status: str | None = None
    new_status: str | None = None
    roles_updated: bool = False


class ResetTimerResponse(BaseModel):
    """Response for reset reverify timer operation."""

    success: bool
    message: str


@router.post("/user/{user_id}/recheck", response_model=RecheckUserResponse)
async def recheck_user(
    user_id: str,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Trigger a reverification check for a specific user.

    This calls the bot's internal API to run the same verification logic
    as the /recheck slash command.

    Requires: Admin role

    Args:
        user_id: Discord user ID (as string)

    Returns:
        RecheckUserResponse with verification results
    """
    # Use validation utilities for consistent ID parsing and guild validation
    user_id_int, guild_id_int = ensure_user_and_guild_ids(user_id, current_user)

    # Get user's current verification status before recheck
    cursor = await db.execute(
        "SELECT rsi_handle, main_orgs, affiliate_orgs FROM verification WHERE user_id = ?",
        (user_id_int,),
    )
    row = await cursor.fetchone()
    row[0] if row else None

    # Determine old status from org lists
    import json

    from core.guild_settings import get_organization_settings

    org_settings = await get_organization_settings(db, guild_id_int)
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    # Helper to derive status from JSON org lists
    def _get_status_from_json(main_orgs_json, affiliate_orgs_json, sid):
        if main_orgs_json is None and affiliate_orgs_json is None:
            return "unknown"
        mo = json.loads(main_orgs_json) if main_orgs_json else []
        ao = json.loads(affiliate_orgs_json) if affiliate_orgs_json else []
        return derive_membership_status(mo, ao, sid or "TEST")

    old_status = _get_status_from_json(
        row[1] if row else None,
        row[2] if row else None,
        organization_sid,
    )

    # Call internal API to trigger recheck
    try:
        result = await internal_api.recheck_user(
            guild_id=guild_id_int,
            user_id=user_id_int,
            admin_user_id=current_user.user_id,
        )
    except Exception as e:
        # Log failed action
        await log_admin_action(
            admin_user_id=int(current_user.user_id),
            guild_id=guild_id_int,
            action="RECHECK_USER",
            target_user_id=user_id_int,
            details={"error": str(e)},
            status="error",
        )
        raise HTTPException(status_code=500, detail=f"Recheck failed: {e!s}")

    # Get new verification status after recheck
    cursor = await db.execute(
        "SELECT rsi_handle, main_orgs, affiliate_orgs FROM verification WHERE user_id = ?",
        (user_id_int,),
    )
    row = await cursor.fetchone()
    new_rsi_handle = row[0] if row else None
    new_status = _get_status_from_json(
        row[1] if row else None,
        row[2] if row else None,
        organization_sid,
    )

    # Determine if roles were updated
    roles_updated = result.get("roles_updated", False) or (old_status != new_status)

    # Log successful action
    await log_admin_action(
        admin_user_id=int(current_user.user_id),
        guild_id=guild_id_int,
        action="RECHECK_USER",
        target_user_id=user_id_int,
        details={
            "rsi_handle": new_rsi_handle,
            "old_status": old_status,
            "new_status": new_status,
            "roles_updated": roles_updated,
        },
        status="success",
    )

    return RecheckUserResponse(
        success=True,
        message=result.get("message", "User rechecked successfully"),
        rsi_handle=new_rsi_handle,
        old_status=old_status,
        new_status=new_status,
        roles_updated=roles_updated,
    )


@router.post("/user/{user_id}/reset-timer", response_model=ResetTimerResponse)
async def reset_reverify_timer(
    user_id: str,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
):
    """
    Reset the reverification timer for a specific user.

    Sets needs_reverify_at to 0, clearing any pending reverification requirement.

    Requires: Admin role

    Args:
        user_id: Discord user ID (as string)

    Returns:
        ResetTimerResponse with operation result
    """
    # Use validation utilities for consistent ID parsing and guild validation
    user_id_int, guild_id_int = ensure_user_and_guild_ids(user_id, current_user)

    # Check if user exists in verification table
    cursor = await db.execute(
        "SELECT user_id FROM verification WHERE user_id = ?",
        (user_id_int,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail="User not found in verification database"
        )

    # Reset the timer
    await db.execute(
        "UPDATE verification SET needs_reverify_at = 0, needs_reverify = 0 WHERE user_id = ?",
        (user_id_int,),
    )
    await db.commit()

    # Log the action
    await log_admin_action(
        admin_user_id=int(current_user.user_id),
        guild_id=guild_id_int,
        action="RESET_REVERIFY_TIMER",
        target_user_id=user_id_int,
        details={"success": True},
        status="success",
    )

    return ResetTimerResponse(
        success=True,
        message="Reverification timer reset successfully",
    )


class BulkRecheckRequest(BaseModel):
    """Request for bulk recheck operation."""

    user_ids: list[str]


class BulkRecheckResponse(BaseModel):
    """Response for bulk recheck operation."""

    success: bool
    message: str
    total: int
    successful: int
    failed: int
    errors: list[dict] = []
    results: list[dict] = []
    summary_text: str | None = None
    csv_filename: str | None = None
    csv_content: str | None = None  # Base64-encoded CSV bytes


@router.post("/users/bulk-recheck", response_model=BulkRecheckResponse)
async def bulk_recheck_users(
    request: BulkRecheckRequest,
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Trigger reverification check for multiple users at once.

    This endpoint processes users one at a time to respect rate limits.

    Requires: Admin role

    Args:
        request: BulkRecheckRequest with list of user IDs

    Returns:
        BulkRecheckResponse with operation results
    """
    # Use validation utility for consistent guild validation
    guild_id_int = ensure_active_guild(current_user)

    if not request.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")

    if len(request.user_ids) > MAX_BULK_RECHECK:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot recheck more than {MAX_BULK_RECHECK} users at once",
        )

    successful = 0
    failed = 0
    errors: list[dict] = []
    results: list[dict] = []
    status_rows: list[StatusRow] = []

    for user_id in request.user_ids:
        try:
            user_id_int = parse_snowflake_id(user_id, "User ID")
            recheck_result = await internal_api.recheck_user(
                guild_id=guild_id_int,
                user_id=user_id_int,
                admin_user_id=current_user.user_id,
            )
            successful += 1

            # Extract result fields
            status = recheck_result.get("status")
            diff = recheck_result.get("diff", {})
            roles_updated = recheck_result.get("roles_updated")

            # Capture brief per-user result for UI popup
            results.append(
                {
                    "user_id": str(user_id_int),
                    "status": status,
                    "message": recheck_result.get("message"),
                    "roles_updated": roles_updated,
                    "diff": diff,
                }
            )

            # Build StatusRow for CSV export (following Discord verify check pattern)
            username = (
                diff.get("username_after")
                or diff.get("username_before")
                or f"User_{user_id_int}"
            )
            rsi_handle = diff.get("rsi_handle_after") or diff.get("rsi_handle_before")
            membership_status = status  # "main", "affiliate", "non_member", etc.
            voice_channel = diff.get("voice_channel_after")

            status_rows.append(
                StatusRow(
                    user_id=user_id_int,
                    username=username,
                    rsi_handle=rsi_handle,
                    membership_status=membership_status,
                    last_updated=int(time.time()),
                    voice_channel=voice_channel,
                    rsi_status=status,  # Recheck verified RSI status
                    rsi_checked_at=int(time.time()),
                    rsi_error=None,
                )
            )
        except Exception as e:
            failed += 1
            error_detail = str(e)
            errors.append({"user_id": user_id, "error": error_detail})

            # Add error row to CSV
            status_rows.append(
                StatusRow(
                    user_id=int(user_id) if user_id.isdigit() else 0,
                    username=f"User_{user_id}",
                    rsi_handle=None,
                    membership_status=None,
                    last_updated=None,
                    voice_channel=None,
                    rsi_status=None,
                    rsi_checked_at=int(time.time()),
                    rsi_error=error_detail,
                )
            )

    # Log the bulk action
    await log_admin_action(
        admin_user_id=int(current_user.user_id),
        guild_id=guild_id_int,
        action="BULK_RECHECK",
        details={
            "total": len(request.user_ids),
            "successful": successful,
            "failed": failed,
        },
        status="success" if failed == 0 else "partial",
    )

    # Build summary following Discord verify check embed style
    main_members = sum(1 for r in results if r.get("status") == "main")
    affiliates = sum(1 for r in results if r.get("status") == "affiliate")
    non_members = sum(1 for r in results if r.get("status") == "non_member")
    unverified = sum(1 for r in results if r.get("status") in ("unknown", "unverified"))

    summary_lines = [
        "Bulk Recheck Complete",
        "",
        f"Requested by: {current_user.username} (Admin)",
        f"Checked: {len(request.user_ids)} users",
        "",
        "Results:",
        f"  • Verified/Main: {main_members}",
        f"  • Affiliate: {affiliates}",
        f"  • Non-Member: {non_members}",
        f"  • Unverified: {unverified}",
        f"  • Successful: {successful}",
        f"  • Failed: {failed}",
    ]

    summary_text = "\n".join(summary_lines)

    # Generate CSV export using the same helper as Discord verify check
    csv_filename = None
    csv_content = None
    csv_bytes = None
    if status_rows:
        try:
            # Get guild name for CSV filename
            guild_name = f"guild_{current_user.active_guild_id}"
            invoker_name = current_user.username or "admin"

            csv_filename, csv_bytes = await write_csv(
                status_rows, guild_name=guild_name, invoker_name=invoker_name
            )

            # Base64 encode for JSON transport
            csv_content = base64.b64encode(csv_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to generate CSV: {e}")

    # Post summary to leadership channel
    if status_rows and csv_bytes and csv_filename and csv_content:
        try:
            # Convert StatusRow namedtuples to dicts for JSON serialization
            status_rows_data = [row.to_dict() for row in status_rows]

            # Post to leadership channel via internal API
            # The internal API will build the embed using the same helper as Discord bulk verification
            response = await internal_api.post_bulk_recheck_summary(
                guild_id=guild_id_int,
                admin_user_id=int(current_user.user_id),
                scope_label="web bulk recheck",
                status_rows=status_rows_data,
                csv_bytes=csv_content,  # Already base64 encoded
                csv_filename=csv_filename,
            )
            logger.info(
                f"Posted bulk recheck summary to leadership channel: {response.get('channel_name')}"
            )
        except Exception as e:
            # Log but don't fail the request if posting fails
            logger.warning(
                f"Failed to post bulk recheck summary to leadership channel: {e}"
            )

    return BulkRecheckResponse(
        success=failed == 0,
        message=f"Rechecked {successful}/{len(request.user_ids)} users successfully",
        total=len(request.user_ids),
        successful=successful,
        failed=failed,
        errors=errors,
        results=results,
        summary_text=summary_text,
        csv_filename=csv_filename,
        csv_content=csv_content,
    )
