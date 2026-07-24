"""EventRoleRepository — per-event role slots.

All methods are guild-scoped. Roles are ordered by sort_order, then created_at.
Deletes are hard deletes; the event_role_signups FK cascades on delete.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from services.db.database import Database

if TYPE_CHECKING:
    import aiosqlite

    from .types import EventRoleRecord


def _optional_str(value: object | None) -> str | None:
    """Normalize an optional SQLite text value."""
    return str(value) if value is not None else None


def _row_to_role(row: aiosqlite.Row) -> EventRoleRecord:
    """Convert an event_roles row into an API-facing dict."""
    capacity = row["capacity"]
    return {
        "id": int(row["id"]),
        "guild_id": int(row["guild_id"]),
        "event_id": int(row["event_id"]),
        "name": str(row["name"]),
        "emoji": _optional_str(row["emoji"]),
        "description": _optional_str(row["description"]),
        "capacity": int(capacity) if capacity is not None else None,
        "sort_order": int(row["sort_order"]),
        "locked": bool(row["locked"]),
        "created_at": int(row["created_at"]),
        "updated_at": int(row["updated_at"]),
    }


# Mutable, coordinator-settable columns and their incoming payload keys.
_UPDATABLE_FIELDS = (
    "name",
    "emoji",
    "description",
    "capacity",
    "sort_order",
    "locked",
)


class EventRoleRepository:
    """Repository for the event_roles table."""

    async def list_roles(
        self, guild_id: int, event_id: int
    ) -> list[EventRoleRecord]:
        """Return all roles for an event ordered by sort_order, then created_at."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM event_roles
                WHERE guild_id = ? AND event_id = ?
                ORDER BY sort_order ASC, created_at ASC, id ASC
                """,
                (guild_id, event_id),
            )
            rows = await cursor.fetchall()
            return [_row_to_role(row) for row in rows]

    async def get_role(
        self, guild_id: int, role_id: int
    ) -> EventRoleRecord | None:
        """Return a single role by ID scoped to a guild, or None if absent."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM event_roles WHERE guild_id = ? AND id = ?",
                (guild_id, role_id),
            )
            row = await cursor.fetchone()
            return _row_to_role(row) if row is not None else None

    async def create_role(
        self,
        guild_id: int,
        event_id: int,
        data: dict[str, object | None],
        created_by_user_id: str | None = None,
    ) -> EventRoleRecord:
        """Insert a new role slot for an event and return it."""
        now = int(time.time())
        capacity = data.get("capacity")
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO event_roles (
                    guild_id, event_id, name, emoji, description, capacity,
                    sort_order, locked, created_at, updated_at,
                    created_by_user_id, updated_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    event_id,
                    str(data.get("name") or ""),
                    data.get("emoji"),
                    data.get("description"),
                    int(str(capacity)) if capacity is not None else None,
                    int(str(data.get("sort_order") or 0)),
                    1 if data.get("locked") else 0,
                    now,
                    now,
                    created_by_user_id,
                    created_by_user_id,
                ),
            )
            role_id = cursor.lastrowid
            await db.commit()
        if role_id is None:
            raise RuntimeError("Failed to create event role")
        role = await self.get_role(guild_id, int(role_id))
        if role is None:
            raise RuntimeError("Created event role could not be loaded")
        return role

    async def update_role(
        self,
        guild_id: int,
        role_id: int,
        data: dict[str, object | None],
        updated_by_user_id: str | None = None,
    ) -> EventRoleRecord | None:
        """Update mutable fields on a role. Only keys present in data are changed.

        Returns the updated role, or None if no matching role exists.
        """
        set_clauses: list[str] = []
        params: list[object | None] = []
        for field in _UPDATABLE_FIELDS:
            if field not in data:
                continue
            value = data[field]
            if field == "locked":
                value = 1 if value else 0
            elif field == "capacity":
                value = int(str(value)) if value is not None else None
            elif field == "sort_order":
                value = int(str(value or 0))
            set_clauses.append(f"{field} = ?")
            params.append(value)

        if not set_clauses:
            return await self.get_role(guild_id, role_id)

        set_clauses.append("updated_at = ?")
        params.append(int(time.time()))
        set_clauses.append("updated_by_user_id = ?")
        params.append(updated_by_user_id)
        params.extend([guild_id, role_id])

        async with Database.get_connection() as db:
            cursor = await db.execute(
                f"UPDATE event_roles SET {', '.join(set_clauses)} "
                "WHERE guild_id = ? AND id = ?",
                tuple(params),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None
        return await self.get_role(guild_id, role_id)

    async def delete_role(self, guild_id: int, role_id: int) -> bool:
        """Hard-delete a role (cascades to event_role_signups). Returns success."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM event_roles WHERE guild_id = ? AND id = ?",
                (guild_id, role_id),
            )
            await db.commit()
            return cursor.rowcount > 0


def get_event_role_repository() -> EventRoleRepository:
    """Dependency provider for EventRoleRepository."""
    return EventRoleRepository()
