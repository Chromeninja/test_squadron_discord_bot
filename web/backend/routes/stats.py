"""
Statistics endpoints for dashboard overview.
"""

import contextlib

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_staff,
)
from core.pagination import is_all_guilds_mode
from core.schemas import StatsOverview, StatsResponse, StatusCounts, UserProfile
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/overview", response_model=StatsResponse)
async def get_stats_overview(
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get dashboard statistics overview.

    Returns verification totals, status breakdown, and active voice channel count.

    The "unknown" count represents all guild members who have not completed verification,
    calculated as: total_guild_members - (main + affiliate + non_member).

    In All Guilds mode (bot owner only), returns aggregated stats across all guilds.

    Requires: Staff role or higher

    Returns:
        StatsResponse with overview data
    """
    # Check if in All Guilds mode
    cross_guild = is_all_guilds_mode(current_user.active_guild_id)

    # Get guild_id from user session
    if cross_guild or not current_user.active_guild_id:
        # In cross-guild mode or no active guild, we can't get single guild member count
        guild_id = None
    else:
        guild_id = int(current_user.active_guild_id)

    # Fetch total guild member count from internal API
    total_guild_members = 0
    # Indicates that the breakdown is aggregated across guilds and per-guild "unknown" is not well-defined
    cross_guild_breakdown = cross_guild
    if cross_guild:
        # In cross-guild mode, aggregate member counts from all guilds
        try:
            guilds_response = await internal_api.get_guilds()
            for guild_info in guilds_response:
                try:
                    guild_id_value = guild_info.get("guild_id")
                    if guild_id_value is not None:
                        guild_stats = await internal_api.get_guild_stats(int(guild_id_value))
                        total_guild_members += guild_stats.get("member_count", 0)
                except Exception:
                    pass  # Skip individual guild failures
        except Exception:
            total_guild_members = 0
    elif guild_id:
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

    # Count by membership status derived from org lists for this guild
    import json

    from services.db.database import derive_membership_status

    status_counts = StatusCounts()

    if cross_guild_breakdown:
        # In cross-guild mode, we can't derive status per specific guild org
        # The "unknown" count (unverified guild members) is not well-defined across guilds
        # Set unknown=0 to avoid misleading numbers; consumers should rely on total_verified
        status_counts.unknown = 0
    else:
        # Get guild's tracked organization SID
        guild_org_sid = "TEST"  # Default
        if guild_id:
            cursor = await db.execute(
                "SELECT value FROM guild_settings WHERE guild_id = ? AND key = 'organization.sid'",
                (guild_id,),
            )
            row = await cursor.fetchone()
            if row and row[0]:
                guild_org_sid = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                if isinstance(guild_org_sid, str) and guild_org_sid.startswith('"'):
                    with contextlib.suppress(Exception):
                        guild_org_sid = json.loads(guild_org_sid)

        # Derive status for each verified user based on their org lists
        cursor = await db.execute("SELECT main_orgs, affiliate_orgs FROM verification")
        rows = await cursor.fetchall()

        for row in rows:
            main_orgs_json, affiliate_orgs_json = row
            # Treat NULL org lists as "unknown" (not counted in main/affiliate/non_member)
            if main_orgs_json is None and affiliate_orgs_json is None:
                continue
            main_orgs = json.loads(main_orgs_json) if main_orgs_json else None
            affiliate_orgs = (
                json.loads(affiliate_orgs_json) if affiliate_orgs_json else None
            )

            status = derive_membership_status(main_orgs, affiliate_orgs, guild_org_sid)

            if status == "main":
                status_counts.main += 1
            elif status == "affiliate":
                status_counts.affiliate += 1
            elif status == "non_member":
                status_counts.non_member += 1

        # Calculate true unverified count: all guild members who aren't verified
        # This includes both users with status="unknown" in DB AND users not in DB at all
        if total_guild_members > 0:
            verified_count = (
                status_counts.main + status_counts.affiliate + status_counts.non_member
            )
            status_counts.unknown = max(0, total_guild_members - verified_count)

    # Active voice channels
    cursor = await db.execute("SELECT COUNT(*) FROM voice_channels WHERE is_active = 1")
    row = await cursor.fetchone()
    voice_active_count = row[0] if row else 0

    overview = StatsOverview(
        total_verified=total_verified,
        by_status=status_counts,
        voice_active_count=voice_active_count,
    )

    return StatsResponse(success=True, data=overview)
