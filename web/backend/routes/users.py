"""
User search and management endpoints for verification records.
"""

import csv
import io
import json
import logging
import time
from datetime import UTC, datetime

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_fresh_guild_access,
    require_staff,
)
from core.guild_members import derive_status_from_orgs, fetch_guild_member_ids
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
    EnrichedUser,
    ExportUsersRequest,
    ResolveIdsRequest,
    UserDetailsResponse,
    UsersListResponse,
    _VERIFICATION_COLUMNS,
    _build_search_where,
    _build_status_filters,
    _derive_and_filter,
    _enriched_user_from_row,
    _escape_like,
    _get_member_with_cache,
    _list_users_cross_guild,
    _list_users_single_guild,
    _paginate,
    _parse_verification_row,
    _placeholder_member,
    _split_comma_param,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

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




# Cached available orgs response: (expires_at, org_list)
_orgs_cache: tuple[float, list[str]] | None = None
_ORGS_CACHE_TTL = 60


@router.get("/orgs")
async def get_available_orgs(
    db=Depends(get_db),
    _current_user: UserProfile = Depends(require_staff()),
) -> dict:
    """Return the distinct set of org SIDs across all verification records.

    Results are cached for 60 seconds to avoid repeated full-table scans.
    """
    global _orgs_cache
    now = time.time()
    if _orgs_cache and _orgs_cache[0] > now:
        return {"success": True, "orgs": _orgs_cache[1]}

    cursor = await db.execute(
        "SELECT DISTINCT value FROM ("
        "  SELECT value FROM verification, json_each(main_orgs)"
        "  UNION"
        "  SELECT value FROM verification, json_each(affiliate_orgs)"
        ") WHERE value != 'REDACTED' ORDER BY value"
    )
    rows = await cursor.fetchall()
    org_list = [row[0] for row in rows]

    _orgs_cache = (now + _ORGS_CACHE_TTL, org_list)
    return {"success": True, "orgs": org_list}


@router.post("/resolve-ids")
async def resolve_filtered_ids(
    request: ResolveIdsRequest,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
) -> dict:
    """Resolve the set of Discord user IDs matching the given filters.

    Returns up to ``limit`` IDs (default 100) after applying status,
    search, org, and exclusion filters against the full dataset for
    the active guild.  This is used by the frontend for server-side
    "select all filtered" bulk actions that span multiple pages.

    Requires: Staff role or higher
    """
    max_ids = min(request.limit or 100, 500)

    if not current_user.active_guild_id:
        return {"user_ids": [], "total": 0}

    if is_all_guilds_mode(current_user.active_guild_id):
        return {"user_ids": [], "total": 0}

    guild_id = int(current_user.active_guild_id)
    status_filters = _build_status_filters(list_values=request.membership_statuses)
    search_text = request.search.strip() if request.search else None
    org_sids = request.orgs or []
    where_clause, where_params = _build_search_where(search_text, org_sids)

    try:
        guild_member_ids = await fetch_guild_member_ids(internal_api, guild_id)
    except Exception as exc:
        logger.warning(
            "Failed to fetch guild member IDs for resolve-ids in guild %s",
            guild_id,
            exc_info=exc,
        )
        return {"user_ids": [], "total": 0}

    if not guild_member_ids:
        return {"user_ids": [], "total": 0}

    id_list = list(guild_member_ids)
    placeholders = ",".join("?" * len(id_list))
    member_filter = f"user_id IN ({placeholders})"
    combined_where = (
        f"{member_filter} AND {where_clause}" if where_clause else member_filter
    )
    query = (
        f"SELECT {_VERIFICATION_COLUMNS} FROM verification "
        f"WHERE {combined_where} ORDER BY last_updated DESC"
    )
    cursor = await db.execute(query, id_list + where_params)
    rows = await cursor.fetchall()

    org_settings = await get_organization_settings(db, guild_id)
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    derived = _derive_and_filter(rows, status_filters, organization_sid)
    exclude_set = set(request.exclude_ids or [])

    user_ids: list[str] = []
    for parsed, _status in derived:
        uid = str(parsed["user_id"])
        if uid in exclude_set:
            continue
        user_ids.append(uid)
        if len(user_ids) >= max_ids:
            break

    filtered_total = sum(
        1 for parsed, _ in derived if str(parsed["user_id"]) not in exclude_set
    )

    return {"user_ids": user_ids, "total": filtered_total}


@router.post("/export")
async def export_users(
    request: ExportUsersRequest,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Export users to CSV.

    Exports either:
    - Selected users (if selected_ids provided)
    - All filtered users (if membership_status filter provided)
    - All users (if no filters)

    Requires: Staff role or higher

    Returns:
        CSV file as streaming response
    """
    if not current_user.active_guild_id:
        # Return empty CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "discord_id",
                "username",
                "membership_status",
                "rsi_handle",
                "community_moniker",
                "joined_at",
                "created_at",
                "last_updated",
                "needs_reverify",
                "role_ids",
                "role_names",
                "main_orgs",
                "affiliate_orgs",
            ]
        )

        csv_content = output.getvalue()
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=members_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
            },
        )

    guild_id = int(current_user.active_guild_id)

    # Build query based on filters
    status_filters = _build_status_filters(
        list_values=request.membership_statuses,
        single_value=request.membership_status,
    )
    search_text = request.search.strip() if request.search else None
    org_sids = request.orgs or []

    # Build SQL WHERE for search + org conditions
    where_clause, where_params = _build_search_where(search_text, org_sids)

    # Filter by guild membership (only export users who are actually in this guild)
    guild_member_ids: set[int] | None = None
    try:
        guild_member_ids = await fetch_guild_member_ids(internal_api, guild_id)
    except Exception:
        logger.warning(
            "Failed to fetch guild member IDs for export, exporting unfiltered"
        )

    if request.selected_ids:
        placeholders = ",".join("?" * len(request.selected_ids))
        user_ids = [int(uid) for uid in request.selected_ids]
        id_where = f"user_id IN ({placeholders})"
        combined_where = f"{id_where} AND {where_clause}" if where_clause else id_where
        query = (
            f"SELECT {_VERIFICATION_COLUMNS} FROM verification "
            f"WHERE {combined_where} ORDER BY last_updated DESC"
        )
        cursor = await db.execute(query, user_ids + where_params)
    else:
        where_sql = f"WHERE {where_clause}" if where_clause else ""
        query = (
            f"SELECT {_VERIFICATION_COLUMNS} FROM verification "
            f"{where_sql} ORDER BY last_updated DESC"
        )
        cursor = await db.execute(query, where_params)

    rows_all = await cursor.fetchall()
    exclude_ids = {str(uid) for uid in (request.exclude_ids or [])}

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "discord_id",
            "username",
            "membership_status",
            "rsi_handle",
            "community_moniker",
            "joined_at",
            "created_at",
            "last_updated",
            "needs_reverify",
            "role_ids",
            "role_names",
            "main_orgs",
            "affiliate_orgs",
        ]
    )

    # Org settings for derivation
    org_settings = await get_organization_settings(db, guild_id)
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    # Data rows with Discord enrichment and role filtering
    for row in rows_all:
        user_id = row[0]

        # Skip users not in guild (only when not using selected_ids)
        if (
            not request.selected_ids
            and guild_member_ids is not None
            and user_id not in guild_member_ids
        ):
            continue

        # Skip excluded IDs (only when not using selected_ids)
        if not request.selected_ids and str(user_id) in exclude_ids:
            continue

        try:
            member_data = await _get_member_with_cache(internal_api, guild_id, user_id)
        except Exception:
            member_data = _placeholder_member(user_id)

        roles = member_data.get("roles", [])
        username = member_data.get("username", "Unknown")
        joined_at = member_data.get("joined_at", "")
        created_at = member_data.get("created_at", "")
        role_ids = ",".join(str(r["id"]) for r in roles)
        role_names = ",".join(r["name"] for r in roles)

        # Parse org JSON arrays
        main_orgs_list = json.loads(row[5]) if row[5] else []
        affiliate_orgs_list = json.loads(row[6]) if row[6] else []
        derived_status = derive_status_from_orgs(
            main_orgs_list, affiliate_orgs_list, organization_sid
        )

        # Apply status filters if present (only when not using selected_ids)
        if (
            not request.selected_ids
            and status_filters
            and derived_status not in status_filters
        ):
            continue
        main_orgs_str = ";".join(main_orgs_list) if main_orgs_list else ""
        affiliate_orgs_str = (
            ";".join(affiliate_orgs_list) if affiliate_orgs_list else ""
        )

        writer.writerow(
            [
                str(user_id),
                username,
                derived_status or "",
                row[1] or "",
                row[2] or "",
                joined_at,
                created_at,
                row[3] or "",
                "Yes" if row[4] else "No",
                role_ids,
                role_names,
                main_orgs_str,
                affiliate_orgs_str,
            ]
        )

    csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=members_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )
