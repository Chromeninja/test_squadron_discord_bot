"""Membership status helpers for organization SID resolution."""

from __future__ import annotations

import json


def derive_membership_status(
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    target_sid: str = "TEST",
) -> str:
    """Derive membership status from organization SID lists.

    Returns one of: ``main``, ``affiliate``, or ``non_member``.
    """
    # Normalize potentially missing values to simplify downstream checks.
    normalized_main = main_orgs or []
    normalized_affiliate = affiliate_orgs or []

    target_upper = target_sid.upper()
    non_redacted_main = [
        sid.upper() for sid in normalized_main if sid and sid != "REDACTED"
    ]
    non_redacted_affiliate = [
        sid.upper() for sid in normalized_affiliate if sid and sid != "REDACTED"
    ]

    if target_upper in non_redacted_main:
        return "main"

    if target_upper in non_redacted_affiliate:
        return "affiliate"

    return "non_member"


async def get_cross_guild_membership_status(user_id: int) -> str:
    """Determine a user's highest membership status across tracked guild orgs."""
    from .database import Database

    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT main_orgs, affiliate_orgs FROM verification WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return "non_member"

        main_orgs_json, affiliate_orgs_json = row
        main_orgs = json.loads(main_orgs_json) if main_orgs_json else []
        affiliate_orgs = json.loads(affiliate_orgs_json) if affiliate_orgs_json else []

        main_orgs = [sid for sid in main_orgs if sid != "REDACTED"]
        affiliate_orgs = [sid for sid in affiliate_orgs if sid != "REDACTED"]

        if not main_orgs and not affiliate_orgs:
            return "non_member"

        all_user_orgs = set(main_orgs + affiliate_orgs)

        tracked_orgs_query = """
            SELECT json_extract(value, '$') as org_sid
            FROM guild_settings
            WHERE key = 'organization.sid'
            AND json_extract(value, '$') IS NOT NULL
        """
        cursor = await db.execute(tracked_orgs_query)
        tracked_sids_rows = await cursor.fetchall()
        tracked_sids = {
            result_row[0].strip('"').upper() for result_row in tracked_sids_rows if result_row[0]
        }

        tracked_user_orgs = all_user_orgs.intersection(tracked_sids)

        if not tracked_user_orgs:
            return "non_member"

        normalized_main_orgs = {sid.upper() for sid in main_orgs}
        for org_sid in tracked_user_orgs:
            if org_sid in normalized_main_orgs:
                return "main"

        return "affiliate"
