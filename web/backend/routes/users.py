"""
User search and management endpoints for verification records.
"""

import csv
import io
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_fresh_guild_access,
    require_staff,
)
from core.guild_settings import get_organization_settings
from core.schemas import UserProfile, UserSearchResponse, VerificationRecord
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.db.database import derive_membership_status

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


def _derive_status_from_orgs(
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    organization_sid: str | None,
) -> str:
    """Derive membership status from org lists and optional org SID.

    - If SID provided, match exactly; else fallback to non-empty list heuristic.
    - Both lists empty => non_member; both None => unknown.
    - REDACTED entries are filtered out (treated as unknown orgs).
    """
    if main_orgs is None and affiliate_orgs is None:
        return "unknown"

    return derive_membership_status(main_orgs or [], affiliate_orgs or [], organization_sid or "TEST")


@router.get(
    "/search",
    response_model=UserSearchResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def search_users(
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
            """
            SELECT
                user_id, rsi_handle,
                community_moniker, last_updated, needs_reverify,
                main_orgs, affiliate_orgs
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
                    user_id, rsi_handle,
                    community_moniker, last_updated, needs_reverify,
                    main_orgs, affiliate_orgs
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
                    user_id, rsi_handle,
                    community_moniker, last_updated, needs_reverify,
                    main_orgs, affiliate_orgs
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
    # Derive membership status for the current guild if possible
    org_settings = await get_organization_settings(
        db, int(current_user.active_guild_id) if current_user.active_guild_id else 0
    )
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    for row in rows:
        main_orgs = json.loads(row[5]) if row[5] else None
        affiliate_orgs = json.loads(row[6]) if row[6] else None
        derived_status = _derive_status_from_orgs(
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
    main_orgs: list[str] | None = None
    affiliate_orgs: list[str] | None = None
    # Cross-guild fields (populated in All Guilds mode)
    guild_id: str | None = None
    guild_name: str | None = None


class UsersListResponse(BaseModel):
    """Response for paginated users list."""

    success: bool = True
    items: list[EnrichedUser]
    total: int
    page: int
    page_size: int
    total_pages: int
    is_cross_guild: bool = False  # True when in All Guilds mode


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
    page_size: int = Query(25, ge=1, le=200, description="Items per page (max 200)"),
    membership_status: str | None = Query(
        None,
        description="Single membership status filter (deprecated in favor of membership_statuses)",
    ),
    membership_statuses: str | None = Query(
        None,
        description="Comma-separated membership statuses (e.g., main,affiliate)",
    ),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Get paginated list of users with Discord enrichment.

    Combines verification table data with Discord member information.
    When 'unknown' status is selected, fetches all Discord members and filters out verified ones.
    Bot owners in "All Guilds" mode can view users across all guilds (read-only).

    Query params:
    - page: Page number (1-indexed)
    - page_size: Items per page (default 50, max 200)
    - membership_statuses: Comma-separated list (e.g., "main,affiliate,unknown")

    Note: In single-guild mode, results are filtered to only include users who are
    current members of the guild. In cross-guild mode (bot owner only), all verified
    users are returned without guild membership filtering, and status derivation uses
    a default org SID since no specific guild context is available.

    Requires: Staff role or higher

    Returns:
        UsersListResponse with enriched user data
    """
    from core.pagination import (
        DEFAULT_PAGE_SIZE_USERS,
        MAX_PAGE_SIZE_USERS,
        clamp_page_size,
        is_all_guilds_mode,
    )

    # Apply pagination caps
    page_size = clamp_page_size(page_size, DEFAULT_PAGE_SIZE_USERS, MAX_PAGE_SIZE_USERS)

    is_cross_guild = is_all_guilds_mode(current_user.active_guild_id)

    if not current_user.active_guild_id:
        return UsersListResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            is_cross_guild=False,
        )

    offset = (page - 1) * page_size

    # Parse filters
    status_filters = _build_status_filters(
        list_values=_split_comma_param(membership_statuses),
        single_value=membership_status,
    )

    # Fetch verification data
    cursor = await db.execute(
        """
        SELECT
            user_id, rsi_handle,
            community_moniker, last_updated, needs_reverify,
            main_orgs, affiliate_orgs
        FROM verification
        ORDER BY last_updated DESC
        """,
    )

    rows_all = await cursor.fetchall()

    if is_cross_guild:
        # Cross-guild mode: Fetch all guilds and build guild metadata map
        try:
            guilds_list = await internal_api.get_guilds()
            _ = {
                str(g.get("guild_id")): g.get("guild_name", f"Guild {g.get('guild_id')}")
                for g in guilds_list
            }  # Reserved for future per-guild enrichment
        except Exception:
            pass  # Guild names not critical for cross-guild view

        # For cross-guild, we show all verified users without guild filtering
        # But we need to figure out which guilds they're in for display purposes
        # For now, we'll show all users with "Multiple" as guild context
        derived_rows: list[tuple] = []
        for row in rows_all:
            main_orgs = json.loads(row[5]) if row[5] else None
            affiliate_orgs = json.loads(row[6]) if row[6] else None
            # Use a default status derivation (no specific guild org SID)
            status = _derive_status_from_orgs(main_orgs, affiliate_orgs, None)
            if status_filters and status not in status_filters:
                continue
            derived_rows.append(
                (
                    row[0],  # user_id
                    row[1],  # rsi_handle
                    status,  # derived status
                    row[2],  # community_moniker
                    row[3],  # last_updated
                    row[4],  # needs_reverify
                    main_orgs,
                    affiliate_orgs,
                    None,  # guild_id (will be determined per-user)
                    None,  # guild_name
                )
            )

        total_filtered = len(derived_rows)
        start = offset
        end = offset + page_size
        rows = derived_rows[start:end]

        # Build items without Discord enrichment (cross-guild can't query member data)
        items: list[EnrichedUser] = []
        for row in rows:
            items.append(
                EnrichedUser(
                    discord_id=str(row[0]),
                    username="Unknown",  # Can't fetch Discord data across guilds
                    discriminator="0000",
                    global_name=None,
                    avatar_url=None,
                    membership_status=row[2],
                    rsi_handle=row[1],
                    community_moniker=row[3],
                    joined_at=None,
                    created_at=None,
                    last_updated=row[4],
                    needs_reverify=bool(row[5]),
                    roles=[],
                    main_orgs=row[6],
                    affiliate_orgs=row[7],
                    guild_id=None,  # Cross-guild: user may be in multiple guilds
                    guild_name="All Guilds",
                )
            )

        total_pages = (
            (total_filtered + page_size - 1) // page_size if total_filtered > 0 else 0
        )

        return UsersListResponse(
            success=True,
            items=items,
            total=total_filtered,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            is_cross_guild=True,
        )

    # Single-guild mode: Only show users who are actually IN the guild
    guild_id = int(current_user.active_guild_id)

    # First, get the set of user IDs who are actually members of this guild
    try:
        # Fetch all guild member IDs (paginated fetches to get all)
        guild_member_ids: set[int] = set()
        page_num = 1
        fetch_size = 1000  # Max supported by API
        while True:
            members_data = await internal_api.get_guild_members(
                guild_id, page=page_num, page_size=fetch_size
            )
            members_list = members_data.get("members", [])
            for m in members_list:
                if m.get("user_id"):
                    guild_member_ids.add(int(m["user_id"]))
            # Check if we got all members
            if len(members_list) < fetch_size:
                break
            page_num += 1
    except Exception:
        # If we can't fetch members, return empty (fail safe)
        return UsersListResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            is_cross_guild=False,
        )

    if not guild_member_ids:
        return UsersListResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            is_cross_guild=False,
        )

    # Get org SID for the specific guild
    org_settings = await get_organization_settings(db, guild_id)
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    # Filter verification rows to only include guild members
    derived_rows = []
    for row in rows_all:
        user_id = row[0]
        # Skip users not in this guild
        if user_id not in guild_member_ids:
            continue

        main_orgs = json.loads(row[5]) if row[5] else None
        affiliate_orgs = json.loads(row[6]) if row[6] else None
        status = _derive_status_from_orgs(main_orgs, affiliate_orgs, organization_sid)
        if status_filters and status not in status_filters:
            continue
        derived_rows.append(
            (
                user_id,  # user_id
                row[1],  # rsi_handle
                status,  # derived status
                row[2],  # community_moniker
                row[3],  # last_updated
                row[4],  # needs_reverify
                main_orgs,
                affiliate_orgs,
            )
        )

    total_filtered = len(derived_rows)
    start = offset
    end = offset + page_size
    rows = derived_rows[start:end]

    # Enrich with Discord data
    items = []
    for row in rows:
        user_id = row[0]
        main_orgs = row[6]
        affiliate_orgs = row[7]

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
                roles=member_data.get("roles", []),
                main_orgs=main_orgs,
                affiliate_orgs=affiliate_orgs,
                guild_id=None,  # Single guild mode doesn't need this
                guild_name=None,
            )
        )

    total_pages = (
        (total_filtered + page_size - 1) // page_size if total_filtered > 0 else 0
    )
    total_value = total_filtered

    return UsersListResponse(
        success=True,
        items=items,
        total=total_value,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        is_cross_guild=False,
    )


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

    if request.selected_ids:
        placeholders = ",".join("?" * len(request.selected_ids))
        user_ids = [int(uid) for uid in request.selected_ids]

        cursor = await db.execute(
            f"""
            SELECT
                user_id, rsi_handle,
                community_moniker, last_updated, needs_reverify,
                main_orgs, affiliate_orgs
            FROM verification
            WHERE user_id IN ({placeholders})
            ORDER BY last_updated DESC
            """,
            user_ids,
        )
    else:
        # Fetch all; we'll filter by derived status in Python
        cursor = await db.execute(
            """
            SELECT
                user_id, rsi_handle,
                community_moniker, last_updated, needs_reverify,
                main_orgs, affiliate_orgs
            FROM verification
            ORDER BY last_updated DESC
            """,
        )

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
        derived_status = _derive_status_from_orgs(
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
