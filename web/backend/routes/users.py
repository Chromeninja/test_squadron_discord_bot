"""
User search and management endpoints for verification records.
"""

import csv
import io
import time
from collections import OrderedDict
from datetime import datetime

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_admin_or_moderator,
)
from core.schemas import UserProfile, UserSearchResponse, VerificationRecord
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

MEMBER_CACHE_TTL_SECONDS = 60
MEMBER_CACHE_MAX_ENTRIES = 2000
_member_cache: "OrderedDict[tuple[int, int], tuple[float, dict]]" = OrderedDict()


def _cache_get_member(guild_id: int, user_id: int) -> dict | None:
    """Return cached Discord member data if not expired."""
    key = (guild_id, user_id)
    entry = _member_cache.get(key)
    if not entry:
        return None

    expires_at, data = entry
    if expires_at < time.time():
        _member_cache.pop(key, None)
        return None

    # Refresh LRU order
    _member_cache.move_to_end(key)
    return data


def _cache_set_member(guild_id: int, user_id: int, data: dict) -> None:
    """Store Discord member data with TTL, enforcing max size."""
    key = (guild_id, user_id)
    _member_cache[key] = (time.time() + MEMBER_CACHE_TTL_SECONDS, data)
    _member_cache.move_to_end(key)

    if len(_member_cache) > MEMBER_CACHE_MAX_ENTRIES:
        _member_cache.popitem(last=False)


async def _get_member_with_cache(
    internal_api: InternalAPIClient,
    guild_id: int,
    user_id: int,
) -> dict:
    """Fetch Discord member data with a simple in-process TTL cache."""
    cached = _cache_get_member(guild_id, user_id)
    if cached:
        return cached

    member_data = await internal_api.get_guild_member(guild_id, user_id)
    _cache_set_member(guild_id, user_id, member_data)
    return member_data


def _split_comma_param(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def _normalize_status(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized == "all":
        return None
    return normalized


def _build_status_filters(
    list_values: list[str] | None = None,
    single_value: str | None = None,
) -> list[str]:
    """Normalize membership status filters while preserving order."""
    raw_values = []
    if single_value:
        raw_values.append(single_value)
    if list_values:
        raw_values.extend(list_values)

    seen: dict[str, None] = {}
    for value in raw_values:
        normalized = _normalize_status(value)
        if normalized is not None and normalized not in seen:
            seen[normalized] = None
    return list(seen.keys())


def _placeholder_member(user_id: int) -> dict:
    """Return fallback member data when Discord lookups fail."""
    return {
        "user_id": user_id,
        "username": "Unknown",
        "discriminator": "0000",
        "global_name": None,
        "avatar_url": None,
        "joined_at": None,
        "created_at": None,
        "roles": [],
    }

router = APIRouter()


@router.get("/search", response_model=UserSearchResponse)
async def search_users(
    query: str = Query("", description="Search by user_id, rsi_handle, or community_moniker"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    Search verification records.

    Searches by:
    - user_id (exact match)
    - rsi_handle (case-insensitive partial match)
    - community_moniker (case-insensitive partial match)

    Requires: Admin or moderator role

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
            """
            SELECT 
                user_id, rsi_handle, membership_status, 
                community_moniker, last_updated, needs_reverify
            FROM verification
            ORDER BY last_updated DESC
            LIMIT ? OFFSET ?
            """,
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
                """
                SELECT 
                    user_id, rsi_handle, membership_status,
                    community_moniker, last_updated, needs_reverify
                FROM verification
                WHERE user_id = ?
                LIMIT ? OFFSET ?
                """,
                (user_id_int, page_size, offset),
            )
            rows = await cursor.fetchall()
        except ValueError:
            # Not a valid integer, search by handle or moniker
            search_pattern = f"%{query}%"

            count_cursor = await db.execute(
                """
                SELECT COUNT(*) FROM verification
                WHERE rsi_handle LIKE ? OR community_moniker LIKE ?
                """,
                (search_pattern, search_pattern),
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            cursor = await db.execute(
                """
                SELECT 
                    user_id, rsi_handle, membership_status,
                    community_moniker, last_updated, needs_reverify
                FROM verification
                WHERE rsi_handle LIKE ? OR community_moniker LIKE ?
                ORDER BY last_updated DESC
                LIMIT ? OFFSET ?
                """,
                (search_pattern, search_pattern, page_size, offset),
            )
            rows = await cursor.fetchall()

    # Convert rows to VerificationRecord objects
    items = []
    for row in rows:
        items.append(
            VerificationRecord(
                user_id=row[0],
                rsi_handle=row[1],
                membership_status=row[2],
                community_moniker=row[3],
                last_updated=row[4],
                needs_reverify=bool(row[5]),
            )
        )

    return UserSearchResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# New schemas for enriched user data
class EnrichedUser(BaseModel):
    """User record enriched with Discord data."""

    discord_id: str
    username: str
    discriminator: str
    global_name: str | None = None
    avatar_url: str | None = None
    membership_status: str | None = None
    rsi_handle: str | None = None
    community_moniker: str | None = None
    joined_at: str | None = None
    created_at: str | None = None
    last_updated: int | None = None
    needs_reverify: bool = False
    roles: list[dict] = []


class UsersListResponse(BaseModel):
    """Response for paginated users list."""

    success: bool = True
    items: list[EnrichedUser]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExportUsersRequest(BaseModel):
    """Request payload for CSV export."""

    membership_status: str | None = None
    membership_statuses: list[str] | None = None
    role_ids: list[int] | None = None
    selected_ids: list[str] | None = None
    exclude_ids: list[str] | None = None


@router.get("", response_model=UsersListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    membership_status: str | None = Query(
        None,
        description="Single membership status filter (deprecated in favor of membership_statuses)",
    ),
    membership_statuses: str | None = Query(
        None,
        description="Comma-separated membership statuses (e.g., main,affiliate)",
    ),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Get paginated list of users with Discord enrichment.

    Combines verification table data with Discord member information.
    When 'unknown' status is selected, fetches all Discord members and filters out verified ones.
    
    Query params:
    - page: Page number (1-indexed)
    - page_size: Items per page (10, 25, 50, or 100)
    - membership_statuses: Comma-separated list (e.g., "main,affiliate,unknown")
    - role_ids: Comma-separated Discord role IDs (e.g., "123,456")

    Requires: Admin or moderator role

    Returns:
        UsersListResponse with enriched user data
    """
    if not current_user.active_guild_id:
        return UsersListResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )

    guild_id = int(current_user.active_guild_id)
    offset = (page - 1) * page_size

    # Parse filters
    status_filters = _build_status_filters(
        list_values=_split_comma_param(membership_statuses),
        single_value=membership_status,
    )

    placeholders_clause = ""
    query_params: list[str] = []
    if status_filters:
        placeholders_clause = ",".join("?" * len(status_filters))

    where_clauses: list[str] = []
    if status_filters:
        where_clauses.append(
            f"LOWER(COALESCE(membership_status, 'unknown')) IN ({placeholders_clause})"
        )
        query_params.extend(status_filters)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_query = f"SELECT COUNT(*) FROM verification {where_sql}"
    count_cursor = await db.execute(count_query, list(query_params))
    count_row = await count_cursor.fetchone()
    base_total = count_row[0] if count_row else 0

    cursor = await db.execute(
        f"""
        SELECT 
            user_id, rsi_handle, membership_status,
            community_moniker, last_updated, needs_reverify
        FROM verification
        {where_sql}
        ORDER BY last_updated DESC
        LIMIT ? OFFSET ?
        """,
        list(query_params) + [page_size, offset],
    )

    rows = await cursor.fetchall()

    # Enrich with Discord data
    items: list[EnrichedUser] = []
    for row in rows:
        user_id = row[0]

        # Fetch Discord member info with caching
        try:
            member_data = await _get_member_with_cache(internal_api, guild_id, user_id)
        except Exception:
            member_data = _placeholder_member(user_id)

        items.append(
            EnrichedUser(
                discord_id=str(user_id),
                username=member_data.get("username", "Unknown"),
                discriminator=member_data.get("discriminator", "0000"),
                global_name=member_data.get("global_name"),
                avatar_url=member_data.get("avatar_url"),
                membership_status=row[2],
                rsi_handle=row[1],
                community_moniker=row[3],
                joined_at=member_data.get("joined_at"),
                created_at=member_data.get("created_at"),
                last_updated=row[4],
                needs_reverify=bool(row[5]),
                roles=member_data.get("roles", [])
            )
        )

    total_pages = (base_total + page_size - 1) // page_size if base_total > 0 else 0
    total_value = base_total

    return UsersListResponse(
        success=True,
        items=items,
        total=total_value,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/export")
async def export_users(
    request: ExportUsersRequest,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Export users to CSV.

    Exports either:
    - Selected users (if selected_ids provided)
    - All filtered users (if membership_status filter provided)
    - All users (if no filters)

    Requires: Admin or moderator role

    Returns:
        CSV file as streaming response
    """
    if not current_user.active_guild_id:
        # Return empty CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "discord_id", "username", "membership_status", "rsi_handle",
            "community_moniker", "joined_at", "created_at", "last_updated",
            "needs_reverify", "role_ids", "role_names"
        ])

        csv_content = output.getvalue()
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=members_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )

    guild_id = int(current_user.active_guild_id)

    # Build query based on filters
    status_filters = _build_status_filters(
        list_values=request.membership_statuses,
        single_value=request.membership_status,
    )

    if request.selected_ids:
        placeholders = ",".join("?" * len(request.selected_ids))
        user_ids = [int(uid) for uid in request.selected_ids]

        cursor = await db.execute(
            f"""
            SELECT 
                user_id, rsi_handle, membership_status,
                community_moniker, last_updated, needs_reverify
            FROM verification
            WHERE user_id IN ({placeholders})
            ORDER BY last_updated DESC
            """,
            user_ids,
        )
    else:
        where_clauses = []
        query_params: list[str] = []
        if status_filters:
            placeholders = ",".join("?" * len(status_filters))
            where_clauses.append(
                f"LOWER(COALESCE(membership_status, 'unknown')) IN ({placeholders})"
            )
            query_params.extend(status_filters)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        cursor = await db.execute(
            f"""
            SELECT 
                user_id, rsi_handle, membership_status,
                community_moniker, last_updated, needs_reverify
            FROM verification
            {where_sql}
            ORDER BY last_updated DESC
            """,
            query_params,
        )

    rows = await cursor.fetchall()
    exclude_ids = {str(uid) for uid in (request.exclude_ids or [])}

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "discord_id", "username", "membership_status", "rsi_handle",
        "community_moniker", "joined_at", "created_at", "last_updated",
        "needs_reverify", "role_ids", "role_names"
    ])

    # Data rows with Discord enrichment and role filtering
    for row in rows:
        user_id = row[0]

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

        writer.writerow([
            str(user_id),
            username,
            row[2] or "",  # membership_status
            row[1] or "",  # rsi_handle
            row[3] or "",  # community_moniker
            joined_at,
            created_at,
            row[4] or "",  # last_updated
            "Yes" if row[5] else "No",  # needs_reverify
            role_ids,
            role_names
        ])

    csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=members_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )
