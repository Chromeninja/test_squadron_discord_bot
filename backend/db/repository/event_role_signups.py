"""EventRoleSignupRepository — per-role signups for events.

All methods are guild-scoped. Withdrawals/removals are hard deletes. Uniqueness
of (guild_id, event_id, role_id, user_id) is enforced at the DB level; the
"one role per event when multiple is disabled" rule is enforced at the service
layer (it depends on the event's allow_multiple_roles flag).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from services.db.database import Database

if TYPE_CHECKING:
    import aiosqlite

    from .types import EventRoleSignupRecord


def _row_to_role_signup(row: aiosqlite.Row) -> EventRoleSignupRecord:
    """Convert an event_role_signups row into an API-facing dict."""
    return {
        "id": int(row["id"]),
        "guild_id": int(row["guild_id"]),
        "event_id": int(row["event_id"]),
        "role_id": int(row["role_id"]),
        "user_id": str(row["user_id"]),
        "created_at": int(row["created_at"]),
        "updated_at": int(row["updated_at"]),
    }


class EventRoleSignupRepository:
    """Repository for the event_role_signups table."""

    async def list_role_signups(
        self, guild_id: int, event_id: int
    ) -> list[EventRoleSignupRecord]:
        """Return all role signups for an event ordered by created_at."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM event_role_signups
                WHERE guild_id = ? AND event_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (guild_id, event_id),
            )
            rows = await cursor.fetchall()
            return [_row_to_role_signup(row) for row in rows]

    async def get_role_signup(
        self, guild_id: int, role_id: int, user_id: str
    ) -> EventRoleSignupRecord | None:
        """Return a single role signup, or None if absent."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM event_role_signups
                WHERE guild_id = ? AND role_id = ? AND user_id = ?
                """,
                (guild_id, role_id, str(user_id)),
            )
            row = await cursor.fetchone()
            return _row_to_role_signup(row) if row is not None else None

    async def count_for_role(self, guild_id: int, role_id: int) -> int:
        """Return the number of signups for a given role (capacity checks)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM event_role_signups
                WHERE guild_id = ? AND role_id = ?
                """,
                (guild_id, role_id),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0

    async def user_role_count_for_event(
        self, guild_id: int, event_id: int, user_id: str
    ) -> int:
        """Return how many roles the user currently holds for an event."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM event_role_signups
                WHERE guild_id = ? AND event_id = ? AND user_id = ?
                """,
                (guild_id, event_id, str(user_id)),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0

    async def create_role_signup(
        self,
        guild_id: int,
        event_id: int,
        role_id: int,
        user_id: str,
        created_by_user_id: str | None = None,
        capacity: int | None = None,
    ) -> EventRoleSignupRecord | None:
        """Insert a role signup. Returns the row, or None if not inserted.

        Locked-role and multiple-role rules are enforced by the service layer.
        Capacity is enforced here atomically: the conditional INSERT ... SELECT
        counts existing signups in the same statement, so concurrent requests
        cannot oversubscribe a role (pass capacity=None for no limit, e.g. for
        coordinator manual assignment). A None return means either the user is
        already signed up or the role is full — callers disambiguate via
        get_role_signup.
        """
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO event_role_signups (
                    guild_id, event_id, role_id, user_id,
                    created_at, updated_at, created_by_user_id, updated_by_user_id
                )
                SELECT ?, ?, ?, ?, ?, ?, ?, ?
                WHERE ? IS NULL
                   OR (
                        SELECT COUNT(*) FROM event_role_signups
                        WHERE guild_id = ? AND role_id = ?
                      ) < ?
                """,
                (
                    guild_id,
                    event_id,
                    role_id,
                    str(user_id),
                    now,
                    now,
                    created_by_user_id,
                    created_by_user_id,
                    capacity,
                    guild_id,
                    role_id,
                    capacity,
                ),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None
        return await self.get_role_signup(guild_id, role_id, user_id)

    async def delete_role_signup(
        self, guild_id: int, role_id: int, user_id: str
    ) -> bool:
        """Hard-delete a single role signup. Returns True if a row was removed."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                DELETE FROM event_role_signups
                WHERE guild_id = ? AND role_id = ? AND user_id = ?
                """,
                (guild_id, role_id, str(user_id)),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_all_for_user_event(
        self, guild_id: int, event_id: int, user_id: str
    ) -> int:
        """Hard-delete all of a user's role signups for an event.

        Used when a coordinator fully removes a user from an event. Returns the
        number of role rows removed.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                DELETE FROM event_role_signups
                WHERE guild_id = ? AND event_id = ? AND user_id = ?
                """,
                (guild_id, event_id, str(user_id)),
            )
            await db.commit()
            return int(cursor.rowcount or 0)


def get_event_role_signup_repository() -> EventRoleSignupRepository:
    """Dependency provider for EventRoleSignupRepository."""
    return EventRoleSignupRepository()
