"""EventSignupRepository — whole-event interest signups.

All methods are guild-scoped: every query filters on guild_id to keep event
signup data isolated per guild. Withdrawals are hard deletes (rows removed).
"""

from __future__ import annotations

import time

from services.db.database import Database


def _row_to_signup(row: object) -> dict[str, object | None]:
    """Convert an event_signups row into an API-facing dict."""
    return {
        "id": int(row["id"]),  # type: ignore[index]
        "guild_id": int(row["guild_id"]),  # type: ignore[index]
        "event_id": int(row["event_id"]),  # type: ignore[index]
        "user_id": str(row["user_id"]),  # type: ignore[index]
        "created_at": int(row["created_at"]),  # type: ignore[index]
        "updated_at": int(row["updated_at"]),  # type: ignore[index]
    }


class EventSignupRepository:
    """Repository for the event_signups table (whole-event interest)."""

    async def get_signup(
        self, guild_id: int, event_id: int, user_id: str
    ) -> dict[str, object | None] | None:
        """Return a single whole-event signup, or None if absent."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM event_signups
                WHERE guild_id = ? AND event_id = ? AND user_id = ?
                """,
                (guild_id, event_id, str(user_id)),
            )
            row = await cursor.fetchone()
            return _row_to_signup(row) if row is not None else None

    async def list_signups(
        self, guild_id: int, event_id: int
    ) -> list[dict[str, object | None]]:
        """Return all whole-event signups for an event ordered by created_at."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM event_signups
                WHERE guild_id = ? AND event_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (guild_id, event_id),
            )
            rows = await cursor.fetchall()
            return [_row_to_signup(row) for row in rows]

    async def count_signups(self, guild_id: int, event_id: int) -> int:
        """Return the number of whole-event signups for an event."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM event_signups
                WHERE guild_id = ? AND event_id = ?
                """,
                (guild_id, event_id),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0

    async def create_signup(
        self,
        guild_id: int,
        event_id: int,
        user_id: str,
        created_by_user_id: str | None = None,
    ) -> dict[str, object | None] | None:
        """Insert a whole-event signup. Returns the row, or None on duplicate.

        Uses INSERT OR IGNORE against the UNIQUE(guild_id, event_id, user_id)
        constraint so duplicate interest is silently prevented. Callers should
        treat a None return as "already signed up".
        """
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO event_signups (
                    guild_id, event_id, user_id,
                    created_at, updated_at, created_by_user_id, updated_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    event_id,
                    str(user_id),
                    now,
                    now,
                    created_by_user_id,
                    created_by_user_id,
                ),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None
        return await self.get_signup(guild_id, event_id, user_id)

    async def delete_signup(self, guild_id: int, event_id: int, user_id: str) -> bool:
        """Hard-delete a whole-event signup. Returns True if a row was removed."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                DELETE FROM event_signups
                WHERE guild_id = ? AND event_id = ? AND user_id = ?
                """,
                (guild_id, event_id, str(user_id)),
            )
            await db.commit()
            return cursor.rowcount > 0


def get_event_signup_repository() -> EventSignupRepository:
    """Dependency provider for EventSignupRepository."""
    return EventSignupRepository()
