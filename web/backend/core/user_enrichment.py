"""User enrichment helpers: member cache, query builders, and list fetchers."""
import asyncio
import json
import logging
import time
from collections import OrderedDict

from core.dependencies import InternalAPIClient
from core.env_config import MEMBER_CACHE_MAX_ENTRIES, MEMBER_CACHE_TTL_SECONDS
from core.guild_members import derive_status_from_orgs, fetch_guild_member_ids
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Shared verification column list for DRY query building
_VERIFICATION_COLUMNS = (
    "user_id, rsi_handle, community_moniker, last_updated, "
    "needs_reverify, main_orgs, affiliate_orgs"
)

# Member cache: (guild_id, user_id) -> (expires_at, member_data)
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


def _parse_verification_row(row: tuple) -> dict:
    """Parse a raw verification row tuple into a structured dict.

    Malformed JSON in org columns is treated as ``None`` rather than
    propagating an exception.
    """

    def _safe_json(value: str | None) -> list[str] | None:
        if not value:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    return {
        "user_id": row[0],
        "rsi_handle": row[1],
        "community_moniker": row[2],
        "last_updated": row[3],
        "needs_reverify": bool(row[4]),
        "main_orgs": _safe_json(row[5]),
        "affiliate_orgs": _safe_json(row[6]),
    }


def _escape_like(text: str) -> str:
    """Escape LIKE-special characters so they match literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_search_where(
    search: str | None,
    org_sids: list[str],
) -> tuple[str, list]:
    """Build SQL WHERE fragments for text search and org filtering.

    Search uses LIKE across multiple columns (handle, moniker, user_id, org JSON).
    Org filtering uses json_each for exact SID matching with AND logic.
    LIKE wildcards in user input are escaped to prevent injection.

    Returns:
        (where_clause, params) — clause is empty string if no filters apply.
    """
    conditions: list[str] = []
    params: list = []

    if search:
        safe = _escape_like(search)
        pattern = f"%{safe}%"
        conditions.append(
            "(CAST(user_id AS TEXT) LIKE ? ESCAPE '\\'"
            " OR rsi_handle LIKE ? ESCAPE '\\'"
            " OR community_moniker LIKE ? ESCAPE '\\'"
            " OR main_orgs LIKE ? ESCAPE '\\'"
            " OR affiliate_orgs LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern] * 5)

    # AND logic: user must be in ALL selected orgs
    for sid in org_sids:
        conditions.append(
            "(EXISTS (SELECT 1 FROM json_each(main_orgs) WHERE value = ?)"
            " OR EXISTS (SELECT 1 FROM json_each(affiliate_orgs) WHERE value = ?))"
        )
        params.extend([sid, sid])

    return (" AND ".join(conditions), params)


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


class UserDetailsResponse(BaseModel):
    """Response model for a single enriched user details request."""

    success: bool = True
    data: EnrichedUser


class ExportUsersRequest(BaseModel):
    """Request payload for CSV export."""

    membership_status: str | None = None
    membership_statuses: list[str] | None = None
    role_ids: list[int] | None = None
    selected_ids: list[str] | None = None
    exclude_ids: list[str] | None = None
    search: str | None = None
    orgs: list[str] | None = None


class ResolveIdsRequest(BaseModel):
    """Request payload for resolving filtered user IDs server-side."""

    membership_statuses: list[str] | None = None
    search: str | None = None
    orgs: list[str] | None = None
    exclude_ids: list[str] | None = None
    limit: int | None = None


def _enriched_user_from_row(
    parsed: dict,
    status: str | None,
    member_data: dict | None = None,
    guild_id: str | None = None,
    guild_name: str | None = None,
) -> "EnrichedUser":
    """Create an EnrichedUser from a parsed verification row and optional Discord data."""
    m = member_data or _placeholder_member(parsed["user_id"])
    return EnrichedUser(
        discord_id=str(parsed["user_id"]),
        username=m.get("username", "Unknown"),
        discriminator=m.get("discriminator", "0000"),
        global_name=m.get("global_name"),
        avatar_url=m.get("avatar_url"),
        membership_status=status,
        rsi_handle=parsed["rsi_handle"],
        community_moniker=parsed["community_moniker"],
        joined_at=m.get("joined_at"),
        created_at=m.get("created_at"),
        last_updated=parsed["last_updated"],
        needs_reverify=parsed["needs_reverify"],
        roles=m.get("roles", []),
        main_orgs=parsed["main_orgs"],
        affiliate_orgs=parsed["affiliate_orgs"],
        guild_id=guild_id,
        guild_name=guild_name,
    )


def _derive_and_filter(
    rows: list[tuple],
    status_filters: list[str],
    organization_sid: str | None,
) -> list[tuple[dict, str]]:
    """Parse verification rows, derive membership status, and filter.

    Returns list of (parsed_row_dict, derived_status) tuples.
    """
    result: list[tuple[dict, str]] = []
    for row in rows:
        parsed = _parse_verification_row(row)
        status = derive_status_from_orgs(
            parsed["main_orgs"], parsed["affiliate_orgs"], organization_sid
        )
        if status_filters and status not in status_filters:
            continue
        result.append((parsed, status))
    return result


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    """Slice items for pagination.

    Returns:
        (page_items, total_count, total_pages)
    """
    total = len(items)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    offset = (page - 1) * page_size
    return items[offset : offset + page_size], total, total_pages


async def _list_users_cross_guild(
    db,
    page: int,
    page_size: int,
    status_filters: list[str],
    where_clause: str,
    where_params: list,
) -> UsersListResponse:
    """List users across all guilds (bot owner only, read-only)."""
    where_sql = f"WHERE {where_clause}" if where_clause else ""
    query = (
        f"SELECT {_VERIFICATION_COLUMNS} FROM verification "
        f"{where_sql} ORDER BY last_updated DESC"
    )
    cursor = await db.execute(query, where_params)
    rows = await cursor.fetchall()

    # Status is derived (not stored), so filter in Python after derivation
    derived = _derive_and_filter(rows, status_filters, organization_sid=None)
    page_items, total, total_pages = _paginate(derived, page, page_size)

    items = [
        _enriched_user_from_row(parsed, status, guild_name="All Guilds")
        for parsed, status in page_items
    ]

    return UsersListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        is_cross_guild=True,
    )


async def _list_users_single_guild(
    db,
    internal_api: InternalAPIClient,
    guild_id: int,
    page: int,
    page_size: int,
    status_filters: list[str],
    where_clause: str,
    where_params: list,
) -> UsersListResponse:
    """List users for a single guild with Discord enrichment."""
    empty = UsersListResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
        total_pages=0,
    )

    # Fetch guild member IDs from Discord (cached for 30s)
    try:
        guild_member_ids = await fetch_guild_member_ids(internal_api, guild_id)
    except Exception as exc:
        logger.warning(
            "Failed to fetch guild member IDs for guild %s", guild_id, exc_info=exc
        )
        return empty

    if not guild_member_ids:
        return empty

    # Build WHERE: guild membership + search/org conditions
    # Use parameterized placeholders instead of formatting IDs into the SQL string
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

    # Get org settings for status derivation
    from core.guild_settings import get_organization_settings
    org_settings = await get_organization_settings(db, guild_id)
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    derived = _derive_and_filter(rows, status_filters, organization_sid)
    page_items, total, total_pages = _paginate(derived, page, page_size)

    # Batch-enrich only the current page with Discord data (concurrent)
    async def _safe_get_member(uid: int) -> dict | None:
        try:
            return await _get_member_with_cache(internal_api, guild_id, uid)
        except Exception:
            return None

    member_results = await asyncio.gather(
        *[_safe_get_member(parsed["user_id"]) for parsed, _ in page_items]
    )

    items = [
        _enriched_user_from_row(parsed, status, member_data)
        for (parsed, status), member_data in zip(
            page_items, member_results, strict=False
        )
    ]

    return UsersListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
