"""
Statistics endpoints for dashboard overview.
"""

from fastapi import APIRouter, Depends

from core.dependencies import get_db, require_admin_or_moderator
from core.schemas import StatsOverview, StatsResponse, StatusCounts, UserProfile

router = APIRouter()


@router.get("/overview", response_model=StatsResponse)
async def get_stats_overview(
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    Get dashboard statistics overview.

    Returns verification totals, status breakdown, and active voice channel count.

    Requires: Admin or moderator role

    Returns:
        StatsResponse with overview data
    """
    # Total verified users
    cursor = await db.execute("SELECT COUNT(*) FROM verification")
    row = await cursor.fetchone()
    total_verified = row[0] if row else 0

    # Count by membership status
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
            status_counts.unknown = count

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
