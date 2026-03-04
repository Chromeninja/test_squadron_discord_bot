"""
Statistics endpoints for dashboard overview.
"""

import json
import logging

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_staff,
)
from core.guild_members import (
    count_verified_for_member_ids,
    derive_status_from_orgs,
    fetch_guild_member_ids,
    query_verification_chunked,
)
from core.guild_settings import get_organization_settings
from core.pagination import is_all_guilds_mode
from core.schemas import StatsOverview, StatsResponse, StatusCounts, UserProfile
from fastapi import APIRouter, Depends

router = APIRouter()
logger = logging.getLogger(__name__)


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

    # Resolve guild_id from user session
    if cross_guild or not current_user.active_guild_id:
        guild_id = None
    else:
        guild_id = int(current_user.active_guild_id)

    # ---- Fetch guild member IDs (single-guild only) ----
    guild_member_ids: set[int] | None = None
    if guild_id:
        try:
            guild_member_ids = await fetch_guild_member_ids(internal_api, guild_id)
        except Exception:
            logger.debug(
                "Failed to fetch guild member IDs for guild %s",
                guild_id,
                exc_info=True,
            )
            guild_member_ids = None

    # ---- Total guild member count (for "unknown" calculation) ----
    total_guild_members = 0
    if cross_guild:
        try:
            guilds_response = await internal_api.get_guilds()
            for guild_info in guilds_response:
                try:
                    guild_id_value = guild_info.get("guild_id")
                    if guild_id_value is not None:
                        guild_stats = await internal_api.get_guild_stats(
                            int(guild_id_value)
                        )
                        total_guild_members += guild_stats.get("member_count", 0)
                except Exception:
                    logger.debug(
                        "Skipping guild stats fetch failure for guild %s",
                        guild_info.get("guild_id"),
                        exc_info=True,
                    )
        except Exception:
            total_guild_members = 0
    elif guild_id:
        try:
            guild_stats = await internal_api.get_guild_stats(guild_id)
            total_guild_members = guild_stats.get("member_count", 0)
        except Exception:
            total_guild_members = 0

    # ---- Total verified (guild-scoped in single-guild mode) ----
    if cross_guild:
        cursor = await db.execute("SELECT COUNT(*) FROM verification")
        row = await cursor.fetchone()
        total_verified = row[0] if row else 0
    elif guild_member_ids is not None:
        total_verified = await count_verified_for_member_ids(db, guild_member_ids)
    else:
        total_verified = 0

    # ---- Membership status breakdown ----
    status_counts = StatusCounts()

    if cross_guild:
        # Cross-guild: per-guild "unknown" is not well-defined; leave at 0
        status_counts.unknown = 0
    else:
        # Resolve the guild's tracked organization SID via shared helper
        organization_sid: str | None = None
        if guild_id:
            org_settings = await get_organization_settings(db, guild_id)
            organization_sid = (
                org_settings.get("organization_sid") if org_settings else None
            )

        # Query org columns for guild members only (chunked)
        rows = (
            await query_verification_chunked(
                db,
                guild_member_ids,
                "main_orgs, affiliate_orgs",
            )
            if guild_member_ids
            else []
        )

        for main_orgs_json, affiliate_orgs_json in rows:
            # NULL org lists → not yet categorised; skip for status breakdown
            if main_orgs_json is None and affiliate_orgs_json is None:
                continue

            main_orgs = json.loads(main_orgs_json) if main_orgs_json else None
            affiliate_orgs = (
                json.loads(affiliate_orgs_json) if affiliate_orgs_json else None
            )

            status = derive_status_from_orgs(
                main_orgs, affiliate_orgs, organization_sid
            )

            if status == "main":
                status_counts.main += 1
            elif status == "affiliate":
                status_counts.affiliate += 1
            elif status == "non_member":
                status_counts.non_member += 1

        # Unknown = guild members who haven't verified at all
        if total_guild_members > 0:
            verified_count = (
                status_counts.main + status_counts.affiliate + status_counts.non_member
            )
            status_counts.unknown = max(0, total_guild_members - verified_count)

    # ---- Active voice channels ----
    cursor = await db.execute("SELECT COUNT(*) FROM voice_channels WHERE is_active = 1")
    row = await cursor.fetchone()
    voice_active_count = row[0] if row else 0

    overview = StatsOverview(
        total_verified=total_verified,
        by_status=status_counts,
        voice_active_count=voice_active_count,
    )

    return StatsResponse(success=True, data=overview)
