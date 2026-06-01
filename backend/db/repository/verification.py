"""VerificationRepository — wrapper around Database for verification queries.

Delegates to Database class methods where they exist, and issues direct
queries via get_connection() for operations not yet exposed as Database methods.
"""

from __future__ import annotations

import time

from services.db.database import Database


class VerificationRepository:
    """Repository for verification table operations.

    All methods that are guild-scoped require guild_id. Verification is stored
    globally per user (not per guild) in the verification table, but some helper
    methods accept guild_id for context (e.g. user_guild_membership).
    """

    async def get_verification(
        self, guild_id: int, user_id: int
    ) -> dict[str, object | None] | None:
        """Return the global verification state for a user.

        guild_id is accepted for interface consistency but verification data
        is stored globally per user_id — not per guild.
        """
        # Database.get_global_verification_state does not return the full row;
        # issue a direct query to return the complete verification record.
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM verification WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def create_verification(
        self, guild_id: int, data: dict[str, object | None]
    ) -> dict[str, object | None]:
        """Insert or replace a verification row. Returns the created/updated row.

        guild_id accepted for interface consistency; verification is global per user.
        TODO: Database.update_global_verification_state handles upserts but only
        accepts a subset of fields. This method targets the full row.
        """
        import json

        now = int(time.time())
        user_id = data["user_id"]
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO verification (
                    user_id, rsi_handle, main_orgs, affiliate_orgs,
                    community_moniker, last_updated, verification_payload,
                    needs_reverify, needs_reverify_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    rsi_handle = excluded.rsi_handle,
                    main_orgs = excluded.main_orgs,
                    affiliate_orgs = excluded.affiliate_orgs,
                    community_moniker = excluded.community_moniker,
                    last_updated = excluded.last_updated,
                    verification_payload = excluded.verification_payload
                """,
                (
                    user_id,
                    data.get("rsi_handle", ""),
                    json.dumps(data.get("main_orgs"))
                    if data.get("main_orgs") is not None
                    else None,
                    json.dumps(data.get("affiliate_orgs"))
                    if data.get("affiliate_orgs") is not None
                    else None,
                    data.get("community_moniker"),
                    data.get("last_updated", now),
                    json.dumps(data.get("verification_payload"))
                    if data.get("verification_payload") is not None
                    else None,
                ),
            )
            await db.commit()

        result = await self.get_verification(guild_id, int(user_id))  # type: ignore[call-overload]
        if result is None:
            raise RuntimeError("Created verification row could not be loaded")
        return result

    async def update_verification(
        self, guild_id: int, user_id: int, data: dict[str, object | None]
    ) -> dict[str, object | None] | None:
        """Update mutable fields on a verification row. Returns updated row or None.

        guild_id accepted for interface consistency; verification is global per user.
        """
        import json

        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE verification
                SET rsi_handle = COALESCE(?, rsi_handle),
                    main_orgs = COALESCE(?, main_orgs),
                    affiliate_orgs = COALESCE(?, affiliate_orgs),
                    community_moniker = COALESCE(?, community_moniker),
                    last_updated = ?
                WHERE user_id = ?
                """,
                (
                    data.get("rsi_handle"),
                    json.dumps(data["main_orgs"]) if "main_orgs" in data else None,
                    json.dumps(data["affiliate_orgs"])
                    if "affiliate_orgs" in data
                    else None,
                    data.get("community_moniker"),
                    now,
                    user_id,
                ),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None

        return await self.get_verification(guild_id, user_id)

    async def get_all_verified(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all verification rows for users active in a guild.

        Joins user_guild_membership to scope results to a specific guild.
        TODO: Database class does not expose a get_all_verified_for_guild method.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT v.*
                FROM verification v
                INNER JOIN user_guild_membership m ON m.user_id = v.user_id
                WHERE m.guild_id = ?
                ORDER BY v.last_updated DESC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
