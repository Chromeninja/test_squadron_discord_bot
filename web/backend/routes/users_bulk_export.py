"""Bulk ID resolution and CSV export endpoints for users."""

from __future__ import annotations

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
    require_staff,
)
from core.guild_members import derive_status_from_orgs, fetch_guild_member_ids
from core.guild_settings import get_organization_settings
from core.pagination import is_all_guilds_mode
from core.schemas import UserProfile
from core.user_enrichment import (
    _VERIFICATION_COLUMNS,
    ExportUsersRequest,
    ResolveIdsRequest,
    _build_search_where,
    _build_status_filters,
    _derive_and_filter,
    _get_member_with_cache,
    _placeholder_member,
)
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)


_orgs_cache: tuple[float, list[str]] | None = None
_ORGS_CACHE_TTL = 60


@router.get("/orgs")
async def get_available_orgs(
    db=Depends(get_db),
    _current_user: UserProfile = Depends(require_staff()),
) -> dict:
    """Return distinct org SIDs across verification records, cached for 60s."""
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
    """Resolve Discord user IDs matching active filters for bulk actions."""
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
    combined_where = f"{member_filter} AND {where_clause}" if where_clause else member_filter
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
    """Export users to CSV, preserving existing filter semantics."""
    if not current_user.active_guild_id:
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
                "Content-Disposition": (
                    "attachment; filename="
                    f"members_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
                )
            },
        )

    guild_id = int(current_user.active_guild_id)
    status_filters = _build_status_filters(
        list_values=request.membership_statuses,
        single_value=request.membership_status,
    )
    search_text = request.search.strip() if request.search else None
    org_sids = request.orgs or []
    where_clause, where_params = _build_search_where(search_text, org_sids)

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

    org_settings = await get_organization_settings(db, guild_id)
    organization_sid = org_settings.get("organization_sid") if org_settings else None

    for row in rows_all:
        user_id = row[0]

        if (
            not request.selected_ids
            and guild_member_ids is not None
            and user_id not in guild_member_ids
        ):
            continue
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
        role_ids = ",".join(str(role["id"]) for role in roles)
        role_names = ",".join(role["name"] for role in roles)

        main_orgs_list = json.loads(row[5]) if row[5] else []
        affiliate_orgs_list = json.loads(row[6]) if row[6] else []
        derived_status = derive_status_from_orgs(
            main_orgs_list,
            affiliate_orgs_list,
            organization_sid,
        )

        if (
            not request.selected_ids
            and status_filters
            and derived_status not in status_filters
        ):
            continue

        main_orgs_str = ";".join(main_orgs_list) if main_orgs_list else ""
        affiliate_orgs_str = ";".join(affiliate_orgs_list) if affiliate_orgs_list else ""

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
            "Content-Disposition": (
                "attachment; filename="
                f"members_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
            )
        },
    )
