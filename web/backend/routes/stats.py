"""
Statistics endpoints for dashboard overview.
"""

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_admin_or_moderator,
)
from core.schemas import StatsOverview, StatsResponse, StatusCounts, UserProfile
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/overview", response_model=StatsResponse)
async def get_stats_overview(
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get dashboard statistics overview.

    Returns verification totals, status breakdown, and active voice channel count.
    
    The "unknown" count represents all guild members who have not completed verification,
    calculated as: total_guild_members - (main + affiliate + non_member).

    Requires: Admin or moderator role

    Returns:
        StatsResponse with overview data
    """
    # Get guild_id from user session
    if not current_user.active_guild_id:
        # Fallback: if no active guild, we can't get member count
        guild_id = None
    else:
        guild_id = int(current_user.active_guild_id)

    # Fetch total guild member count from internal API
    total_guild_members = 0
    if guild_id:
        try:
            guild_stats = await internal_api.get_guild_stats(guild_id)
            total_guild_members = guild_stats.get("member_count", 0)
        except Exception:
            # If internal API call fails, fall back to verification table only
            # (This provides partial data but prevents complete failure)
            total_guild_members = 0

    # Total verified users
    cursor = await db.execute("SELECT COUNT(*) FROM verification")
    row = await cursor.fetchone()
    total_verified = row[0] if row else 0

    # Count by membership status (only users in verification table)
    cursor = await db.execute(
        """
        SELECT 
            membership_status,
            COUNT(*) as count
        FROM verification
        GROUP BY membership_status
        """
    )
    rows = await cursor.fetchall()

    status_counts = StatusCounts()
    for row in rows:
        status = (row[0] or "unknown").lower()
        count = row[1]

        if status == "main":
            status_counts.main = count
        elif status == "affiliate":
            status_counts.affiliate = count
        elif status == "non_member":
            status_counts.non_member = count
        else:
            # Users with status="unknown" or "unverified" in DB
            status_counts.unknown += count

    # Calculate true unverified count: all guild members who aren't verified
    # This includes both users with status="unknown" in DB AND users not in DB at all
    if total_guild_members > 0:
        verified_count = status_counts.main + status_counts.affiliate + status_counts.non_member
        status_counts.unknown = max(0, total_guild_members - verified_count)

    # Active voice channels
    cursor = await db.execute(
        "SELECT COUNT(*) FROM voice_channels WHERE is_active = 1"
    )
    row = await cursor.fetchone()
    voice_active_count = row[0] if row else 0

    overview = StatsOverview(
        total_verified=total_verified,
        by_status=status_counts,
        voice_active_count=voice_active_count,
    )

    return StatsResponse(success=True, data=overview)
