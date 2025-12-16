"""
Admin endpoints for user management (recheck, reset timers).
"""

import asyncio
import base64
import time
import uuid
from typing import Optional, Callable, Awaitable

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

# Throttling settings for bulk operations to avoid overwhelming RSI
# Conservative pacing to prevent circuit breaker trips on large batches
BULK_RECHECK_DELAY_SECONDS = 3.0  # Delay between each recheck request
BULK_RECHECK_BATCH_SIZE = 5  # Users per batch before longer pause
BULK_RECHECK_BATCH_PAUSE_SECONDS = 10.0  # Pause between batches

router = APIRouter()

# In-memory progress store for bulk recheck jobs
# Key: job_id, Value: progress dict

_bulk_recheck_progress: dict[str, dict] = {}


class BulkRecheckProgress(BaseModel):
    """Progress info for a bulk recheck job."""
    job_id: str
    total: int
    processed: int
    successful: int
    failed: int
    status: str  # "running", "complete", "error"
    current_user: Optional[str] = None
    final_response: dict | None = None


class BulkRecheckStartResponse(BaseModel):
    """Response for async bulk recheck start."""

    job_id: str


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


@router.get("/users/bulk-recheck/{job_id}/progress", response_model=BulkRecheckProgress)
async def get_bulk_recheck_progress(
    job_id: str,
    current_user: UserProfile = Depends(require_moderator()),
):
    """
    Get progress for a bulk recheck job.
    
    Args:
        job_id: The job ID returned when starting bulk recheck
        
    Returns:
        BulkRecheckProgress with current progress
    """
    if job_id not in _bulk_recheck_progress:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    
    progress = _bulk_recheck_progress[job_id]
    return BulkRecheckProgress(**progress)


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
    job_id: str | None = None  # Job ID for progress tracking


async def _execute_bulk_recheck(
    job_id: str,
    request: BulkRecheckRequest,
    current_user: UserProfile,
    internal_api: InternalAPIClient,
    progress_hook: Callable[[dict], Awaitable[None]] | None = None,
) -> BulkRecheckResponse:
    """Core bulk recheck logic shared by sync and async modes."""

    guild_id_int = ensure_active_guild(current_user)

    successful = 0
    failed = 0
    errors: list[dict] = []
    results: list[dict] = []
    status_rows: list[StatusRow] = []
    circuit_breaker_hit = False

    total_users = len(request.user_ids)

    logger.info(
        f"Starting bulk recheck for {total_users} users in guild {guild_id_int} "
        f"(throttle: {BULK_RECHECK_DELAY_SECONDS}s delay, batch size {BULK_RECHECK_BATCH_SIZE})"
    )

    # Pre-flight: Check if circuit breaker is already open before starting
    try:
        from helpers.circuit_breaker import get_rsi_circuit_breaker
        circuit_breaker = get_rsi_circuit_breaker({})
        if circuit_breaker.is_open():
            retry_after = int(circuit_breaker.time_until_retry())
            raise HTTPException(
                status_code=503,
                detail=f"RSI service temporarily unavailable. Retry in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
    except ImportError:
        pass  # Circuit breaker not available, proceed anyway

    for idx, user_id in enumerate(request.user_ids):
        # Check for circuit breaker open condition from previous failures
        if circuit_breaker_hit:
            # Skip remaining users and mark as circuit-breaker-skipped
            errors.append({
                "user_id": user_id,
                "error": "Skipped: RSI service temporarily unavailable",
                "circuit_breaker": True,
            })
            failed += 1
            continue

        try:
            user_id_int = parse_snowflake_id(user_id, "User ID")
            recheck_result = await internal_api.recheck_user(
                guild_id=guild_id_int,
                user_id=user_id_int,
                admin_user_id=current_user.user_id,
                log_leadership=False,  # Don't log individual messages for bulk operations
            )
            successful += 1

            # Update progress
            _bulk_recheck_progress[job_id]["processed"] = idx + 1
            _bulk_recheck_progress[job_id]["successful"] = successful
            _bulk_recheck_progress[job_id]["failed"] = failed
            _bulk_recheck_progress[job_id]["current_user"] = str(user_id_int)

            if progress_hook:
                await progress_hook(_bulk_recheck_progress[job_id])

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

            # Detect circuit breaker / 503 from error message or status code
            is_circuit_open = (
                "503" in error_detail
                or "circuit" in error_detail.lower()
                or "temporarily unavailable" in error_detail.lower()
            )

            if is_circuit_open:
                circuit_breaker_hit = True
                logger.warning(
                    f"Circuit breaker detected at user {idx + 1}/{total_users}, "
                    f"skipping remaining {total_users - idx - 1} users"
                )

            errors.append({
                "user_id": user_id,
                "error": error_detail,
                "circuit_breaker": is_circuit_open,
            })

            # Update progress
            _bulk_recheck_progress[job_id]["processed"] = idx + 1
            _bulk_recheck_progress[job_id]["successful"] = successful
            _bulk_recheck_progress[job_id]["failed"] = failed

            if progress_hook:
                await progress_hook(_bulk_recheck_progress[job_id])

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

        # Throttle between requests to avoid overwhelming RSI
        # Skip delay if circuit breaker hit (we're skipping anyway)
        if not circuit_breaker_hit and idx < total_users - 1:
            # Apply batch pause every BULK_RECHECK_BATCH_SIZE users
            if (idx + 1) % BULK_RECHECK_BATCH_SIZE == 0:
                logger.debug(
                    f"Bulk recheck batch pause after {idx + 1}/{total_users} users "
                    f"(pausing {BULK_RECHECK_BATCH_PAUSE_SECONDS}s)"
                )
                await asyncio.sleep(BULK_RECHECK_BATCH_PAUSE_SECONDS)
            else:
                await asyncio.sleep(BULK_RECHECK_DELAY_SECONDS)

    # Log the bulk action
    skipped_count = sum(1 for e in errors if e.get("circuit_breaker"))
    await log_admin_action(
        admin_user_id=int(current_user.user_id),
        guild_id=guild_id_int,
        action="BULK_RECHECK",
        details={
            "total": len(request.user_ids),
            "successful": successful,
            "failed": failed,
            "circuit_breaker_hit": circuit_breaker_hit,
            "skipped_due_to_circuit_breaker": skipped_count,
        },
        status="success" if failed == 0 else ("circuit_breaker" if circuit_breaker_hit else "partial"),
    )

    # Build summary following Discord verify check embed style
    main_members = sum(1 for r in results if r.get("status") == "main")
    affiliates = sum(1 for r in results if r.get("status") == "affiliate")
    non_members = sum(1 for r in results if r.get("status") == "non_member")
    unverified = sum(1 for r in results if r.get("status") in ("unknown", "unverified"))

    summary_lines = [
        "Bulk Recheck Complete" + (" (Partially)" if circuit_breaker_hit else ""),
        "",
        f"Requested by: {current_user.username} (Admin)",
        f"Checked: {len(request.user_ids)} users",
    ]

    if circuit_breaker_hit:
        summary_lines.extend([
            "",
            "⚠️ RSI Service Temporarily Unavailable",
            f"  • Completed before pause: {successful}",
            f"  • Skipped (will retry later): {skipped_count}",
        ])

    summary_lines.extend([
        "",
        "Results:",
        f"  • Verified/Main: {main_members}",
        f"  • Affiliate: {affiliates}",
        f"  • Non-Member: {non_members}",
        f"  • Unverified: {unverified}",
        f"  • Successful: {successful}",
        f"  • Failed: {failed}",
    ])

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

    # Mark job as complete and schedule cleanup
    _bulk_recheck_progress[job_id]["status"] = "complete"
    _bulk_recheck_progress[job_id]["processed"] = total_users

    result = BulkRecheckResponse(
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
        job_id=job_id,
    )

    _bulk_recheck_progress[job_id]["final_response"] = result.model_dump()

    # Schedule cleanup of progress entry after 5 minutes
    async def _cleanup_progress():
        await asyncio.sleep(300)  # 5 minutes
        _bulk_recheck_progress.pop(job_id, None)

    asyncio.create_task(_cleanup_progress())

    return result


@router.post("/users/bulk-recheck", response_model=BulkRecheckResponse)
async def bulk_recheck_users(
    request: BulkRecheckRequest,
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Run bulk recheck synchronously (backward compatible path)."""

    if not request.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")

    if len(request.user_ids) > MAX_BULK_RECHECK:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot recheck more than {MAX_BULK_RECHECK} users at once",
        )

    job_id = str(uuid.uuid4())
    _bulk_recheck_progress[job_id] = {
        "job_id": job_id,
        "total": len(request.user_ids),
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "status": "running",
        "current_user": None,
        "final_response": None,
    }

    return await _execute_bulk_recheck(job_id, request, current_user, internal_api)


@router.post("/users/bulk-recheck/start", response_model=BulkRecheckStartResponse)
async def bulk_recheck_users_start(
    request: BulkRecheckRequest,
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Start bulk recheck asynchronously and return a job ID for polling."""

    if not request.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")

    if len(request.user_ids) > MAX_BULK_RECHECK:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot recheck more than {MAX_BULK_RECHECK} users at once",
        )

    job_id = str(uuid.uuid4())
    _bulk_recheck_progress[job_id] = {
        "job_id": job_id,
        "total": len(request.user_ids),
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "status": "running",
        "current_user": None,
        "final_response": None,
    }

    async def _run_async():
        try:
            await _execute_bulk_recheck(job_id, request, current_user, internal_api)
        except Exception as e:
            # Mark as error but keep some context for the UI
            _bulk_recheck_progress[job_id]["status"] = "error"
            _bulk_recheck_progress[job_id]["final_response"] = {
                "success": False,
                "message": f"Bulk recheck failed: {e}",
                "total": len(request.user_ids),
                "successful": 0,
                "failed": len(request.user_ids),
                "errors": [{"error": str(e), "user_id": "*"}],
                "results": [],
                "summary_text": None,
                "csv_filename": None,
                "csv_content": None,
                "job_id": job_id,
            }

    asyncio.create_task(_run_async())

    return BulkRecheckStartResponse(job_id=job_id)
