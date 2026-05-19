"""User search and management endpoints for verification records."""

import json
import logging

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_fresh_guild_access,
    require_staff,
)
from core.guild_members import derive_status_from_orgs
from core.guild_settings import get_organization_settings
from core.pagination import (
    DEFAULT_PAGE_SIZE_USERS,
    MAX_PAGE_SIZE_USERS,
    clamp_page_size,
    is_all_guilds_mode,
)
from core.rate_limit import limiter
from core.schemas import UserProfile, UserSearchResponse, VerificationRecord
from core.user_enrichment import (
    _VERIFICATION_COLUMNS,
    UserDetailsResponse,
    UsersListResponse,
    _build_search_where,
    _build_status_filters,
    _enriched_user_from_row,
    _escape_like,
    _get_member_with_cache,
    _list_users_cross_guild,
    _list_users_single_guild,
    _parse_verification_row,
    _split_comma_param,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request

logger = logging.getLogger(__name__)


router = APIRouter()


@router.get(
    "/search",
    response_model=UserSearchResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
@limiter.limit("30/minute")
async def search_users(
    request: Request,
    query: str = Query(
        "", description="Search by user_id, rsi_handle, or community_moniker"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
):
    """
    Search verification records.

    Searches by:
    - user_id (exact match)
    - rsi_handle (case-insensitive partial match)
    - community_moniker (case-insensitive partial match)

    Requires: Staff role or higher

    Args:
        query: Search term
        page: Page number (1-indexed)
        page_size: Results per page (max 100)

    Returns:
        UserSearchResponse with paginated results
    """
    offset = (page - 1) * page_size

    if not query:
        # Return all users (paginated)
        count_cursor = await db.execute("SELECT COUNT(*) FROM verification")
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        cursor = await db.execute(
            f"SELECT {_VERIFICATION_COLUMNS} FROM verification"
            " ORDER BY last_updated DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )
        rows = await cursor.fetchall()
    else:
        # Try exact user_id match first
        try:
            user_id_int = int(query)
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM verification WHERE user_id = ?",
                (user_id_int,),
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            cursor = await db.execute(
                f"SELECT {_VERIFICATION_COLUMNS} FROM verification"
                " WHERE user_id = ? LIMIT ? OFFSET ?",
                (user_id_int, page_size, offset),
            )
            rows = await cursor.fetchall()
        except ValueError:
            # Not a valid integer, search by handle or moniker
            search_pattern = f"%{_escape_like(query)}%"

            count_cursor = await db.execute(
                """
                SELECT COUNT(*) FROM verification
                WHERE rsi_handle LIKE ? ESCAPE '\\' OR community_moniker LIKE ? ESCAPE '\\'
                """,
                (search_pattern, search_pattern),
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            cursor = await db.execute(
                f"SELECT {_VERIFICATION_COLUMNS} FROM verification"
                " WHERE rsi_handle LIKE ? ESCAPE '\\' OR community_moniker LIKE ? ESCAPE '\\'"
                " ORDER BY last_updated DESC LIMIT ? OFFSET ?",
                (search_pattern, search_pattern, page_size, offset),
            )
            rows = await cursor.fetchall()

    # Convert rows to VerificationRecord objects
    items = []
    # Derive membership status for the current guild if possible
    org_settings = await get_organization_settings(
        db, int(current_user.active_guild_id) if current_user.active_guild_id else 0
    )
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    for row in rows:
        main_orgs = json.loads(row[5]) if row[5] else None
        affiliate_orgs = json.loads(row[6]) if row[6] else None
        derived_status = derive_status_from_orgs(
            main_orgs, affiliate_orgs, organization_sid
        )
        items.append(
            VerificationRecord(
                user_id=row[0],
                rsi_handle=row[1],
                membership_status=derived_status,
                community_moniker=row[2],
                last_updated=row[3],
                needs_reverify=bool(row[4]),
                main_orgs=main_orgs,
                affiliate_orgs=affiliate_orgs,
            )
        )

    return UserSearchResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=UsersListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=200, description="Items per page (max 200)"),
    membership_status: str | None = Query(
        None,
        description="Single membership status filter (deprecated in favor of membership_statuses)",
    ),
    membership_statuses: str | None = Query(
        None,
        description="Comma-separated membership statuses (e.g., main,affiliate)",
    ),
    search: str | None = Query(
        None,
        description="Search by RSI handle, moniker, Discord ID, or org name",
    ),
    orgs: str | None = Query(
        None,
        description="Comma-separated org SIDs — user must be in ALL (AND logic)",
    ),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Get paginated list of users with Discord enrichment.

    Combines verification table data with Discord member information.
    Supports server-side search and org filtering for large datasets.

    Query params:
    - page / page_size: Pagination controls
    - membership_statuses: Comma-separated status filter (e.g., "main,affiliate")
    - search: Free-text search across RSI handle, moniker, Discord ID, and org names
    - orgs: Comma-separated org SIDs; user must belong to ALL listed orgs (AND logic)

    Bot owners in "All Guilds" mode can view users across all guilds (read-only).

    Requires: Staff role or higher
    """
    page_size = clamp_page_size(page_size, DEFAULT_PAGE_SIZE_USERS, MAX_PAGE_SIZE_USERS)
    is_cross_guild = is_all_guilds_mode(current_user.active_guild_id)

    empty_response = UsersListResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
        total_pages=0,
    )

    if not current_user.active_guild_id:
        return empty_response

    # Parse filters
    status_filters = _build_status_filters(
        list_values=_split_comma_param(membership_statuses),
        single_value=membership_status,
    )
    search_text = search.strip() if search else None
    org_sids = _split_comma_param(orgs)

    # Build SQL WHERE for search + org filters
    where_clause, where_params = _build_search_where(search_text, org_sids)

    if is_cross_guild:
        return await _list_users_cross_guild(
            db, page, page_size, status_filters, where_clause, where_params
        )

    return await _list_users_single_guild(
        db,
        internal_api,
        int(current_user.active_guild_id),
        page,
        page_size,
        status_filters,
        where_clause,
        where_params,
    )


@router.get("/detail/{discord_id}", response_model=UserDetailsResponse)
async def get_user_details(
    discord_id: str,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Return a single Discord-enriched user record for the active guild.

    Uses Discord as source of truth for member profile fields (avatar, roles, joined dates),
    and merges verification fields (RSI/org/status) when a verification row exists.
    """
    if not current_user.active_guild_id:
        raise HTTPException(status_code=400, detail="No active guild selected")

    if is_all_guilds_mode(current_user.active_guild_id):
        raise HTTPException(
            status_code=400,
            detail="User details are unavailable in All Guilds mode",
        )

    try:
        user_id = int(discord_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid Discord user ID") from exc

    guild_id = int(current_user.active_guild_id)

    try:
        member_data = await _get_member_with_cache(internal_api, guild_id, user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Failed to fetch Discord member"
        ) from exc

    cursor = await db.execute(
        f"SELECT {_VERIFICATION_COLUMNS} FROM verification WHERE user_id = ? LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()

    if row:
        parsed = _parse_verification_row(row)
        org_settings = await get_organization_settings(db, guild_id)
        organization_sid = (
            org_settings.get("organization_sid") if org_settings else None
        )
        status = derive_status_from_orgs(
            parsed["main_orgs"], parsed["affiliate_orgs"], organization_sid
        )
    else:
        parsed = {
            "user_id": user_id,
            "rsi_handle": None,
            "community_moniker": None,
            "last_updated": None,
            "needs_reverify": False,
            "main_orgs": None,
            "affiliate_orgs": None,
        }
        status = None

    enriched = _enriched_user_from_row(parsed, status, member_data=member_data)
    return UserDetailsResponse(data=enriched)

