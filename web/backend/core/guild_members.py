"""Shared guild-member utilities used by multiple route modules.

Centralises guild-member-ID fetching (with a TTL cache), chunked
verification-table queries, and membership-status derivation so that
``routes/stats.py`` and ``routes/users.py`` share a single source of truth.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.env_config import GUILD_IDS_CACHE_TTL
from services.db.database import derive_membership_status

if TYPE_CHECKING:
    from core.dependencies import InternalAPIClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GUILD_IDS_CACHE_TTL: int = GUILD_IDS_CACHE_TTL
"""Seconds before cached guild-member-ID sets expire."""

_SQL_CHUNK_SIZE: int = 900
"""Max parameters per SQL ``IN (…)`` clause (stays below SQLite's default
``SQLITE_MAX_VARIABLE_NUMBER`` of 999)."""

# ---------------------------------------------------------------------------
# Guild-member-ID cache
# ---------------------------------------------------------------------------

_guild_ids_cache: dict[int, tuple[float, set[int]]] = {}


async def fetch_guild_member_ids(
    internal_api: InternalAPIClient,
    guild_id: int,
) -> set[int]:
    """Fetch all member IDs for a guild via the internal bot API.

    Results are cached in-process for ``_GUILD_IDS_CACHE_TTL`` seconds to
    avoid repeated HTTP round-trips when multiple endpoints need the same
    data within a short window (e.g. dashboard + users page).
    """
    now = time.time()
    cached = _guild_ids_cache.get(guild_id)
    if cached and cached[0] > now:
        return cached[1]

    member_ids: set[int] = set()
    page_num = 1
    page_size = 1000

    while True:
        data = await internal_api.get_guild_members(
            guild_id, page=page_num, page_size=page_size,
        )
        members = data.get("members", [])
        for member in members:
            user_id = member.get("user_id")
            if user_id is not None:
                member_ids.add(int(user_id))
        if len(members) < page_size:
            break
        page_num += 1

    _guild_ids_cache[guild_id] = (now + _GUILD_IDS_CACHE_TTL, member_ids)
    return member_ids


# ---------------------------------------------------------------------------
# Chunked verification helpers
# ---------------------------------------------------------------------------


async def count_verified_for_member_ids(
    db,
    member_ids: set[int] | list[int],
) -> int:
    """``COUNT(*)`` from the *verification* table for given member IDs.

    The query is split into chunks of ``_SQL_CHUNK_SIZE`` to respect
    SQLite parameter limits on ``IN (…)`` clauses.
    """
    id_list = list(member_ids) if isinstance(member_ids, set) else member_ids
    if not id_list:
        return 0

    total = 0
    for start in range(0, len(id_list), _SQL_CHUNK_SIZE):
        chunk = id_list[start : start + _SQL_CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM verification WHERE user_id IN ({placeholders})",
            chunk,
        )
        row = await cursor.fetchone()
        total += row[0] if row else 0

    return total


async def query_verification_chunked(
    db,
    member_ids: set[int] | list[int],
    columns: str,
    *,
    where_clause: str = "",
    where_params: list | None = None,
) -> list[tuple]:
    """``SELECT <columns> FROM verification`` filtered to *member_ids*.

    Like :func:`count_verified_for_member_ids`, the query is chunked to
    stay within SQLite parameter limits.  Results from all chunks are
    concatenated — **no** ``ORDER BY`` is applied, so callers that need
    ordering must sort in Python afterwards.

    *where_clause* and *where_params* allow additional SQL conditions
    (e.g. search / org filters) to be AND-ed with the member filter.
    """
    id_list = list(member_ids) if isinstance(member_ids, set) else member_ids
    if not id_list:
        return []

    extra_params = where_params or []
    rows: list[tuple] = []

    for start in range(0, len(id_list), _SQL_CHUNK_SIZE):
        chunk = id_list[start : start + _SQL_CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        member_filter = f"user_id IN ({placeholders})"
        combined = (
            f"{member_filter} AND {where_clause}" if where_clause else member_filter
        )
        sql = f"SELECT {columns} FROM verification WHERE {combined}"
        cursor = await db.execute(sql, chunk + extra_params)
        chunk_rows = await cursor.fetchall()
        rows.extend(chunk_rows)

    return rows


# ---------------------------------------------------------------------------
# Membership-status derivation
# ---------------------------------------------------------------------------


def derive_status_from_orgs(
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    organization_sid: str | None,
) -> str:
    """Derive membership status from org lists and the guild's org SID.

    * Both ``None`` → ``"unknown"``
    * No *organization_sid* configured → ``"unknown"``
    * Otherwise delegates to :func:`services.db.database.derive_membership_status`
    """
    if main_orgs is None and affiliate_orgs is None:
        return "unknown"

    if not organization_sid:
        return "unknown"

    return derive_membership_status(main_orgs or [], affiliate_orgs or [], organization_sid)
