"""TicketRepository — wrapper around Database for ticket queries.

Issues raw queries via Database.get_connection() against the tickets table.
Schema (services/db/schema.py): id, guild_id, channel_id, thread_id (NOT NULL
UNIQUE), user_id, category_id, status ('open'|'closed'), closed_by, created_at
(INTEGER unix seconds), closed_at, claimed_by, claimed_at, close_reason,
initial_description, reopened_at, reopened_by, deleted_at.
"""

from __future__ import annotations

import time

from services.db.database import Database


class TicketRepository:
    """Repository for ticket table operations.

    All methods require guild_id to scope queries to a single guild.
    """

    async def get_tickets(
        self, guild_id: int, status: str | None = None
    ) -> list[dict[str, object | None]]:
        """Return non-deleted tickets for a guild, optionally filtered by status."""
        async with Database.get_connection() as db:
            if status is not None:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM tickets
                    WHERE guild_id = ? AND status = ? AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """,
                    (guild_id, status),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM tickets
                    WHERE guild_id = ? AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """,
                    (guild_id,),
                )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_ticket(
        self, guild_id: int, ticket_id: int
    ) -> dict[str, object | None] | None:
        """Return a single ticket by ID for a guild, or None if not found."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM tickets WHERE guild_id = ? AND id = ?",
                (guild_id, ticket_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def create_ticket(
        self, guild_id: int, data: dict[str, object | None]
    ) -> dict[str, object | None]:
        """Insert a new ticket row and return the created row.

        Requires channel_id, thread_id, and user_id in `data` (all NOT NULL in
        the schema; thread_id is also UNIQUE). created_at defaults to now.
        """
        required = ("channel_id", "thread_id", "user_id")
        missing = [k for k in required if data.get(k) is None]
        if missing:
            raise ValueError(
                f"create_ticket missing required field(s): {', '.join(missing)}"
            )

        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO tickets
                    (guild_id, channel_id, thread_id, user_id, category_id,
                     status, initial_description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    data.get("channel_id"),
                    data.get("thread_id"),
                    data.get("user_id"),
                    data.get("category_id"),
                    data.get("status", "open"),
                    data.get("initial_description"),
                    now,
                ),
            )
            row_id = cursor.lastrowid
            await db.commit()

        if row_id is None:
            raise RuntimeError("Failed to create ticket row")

        result = await self.get_ticket(guild_id, int(row_id))
        if result is None:
            raise RuntimeError("Created ticket row could not be loaded")
        return result

    async def update_ticket(
        self, guild_id: int, ticket_id: int, data: dict[str, object | None]
    ) -> dict[str, object | None] | None:
        """Update mutable fields on a ticket row. Returns updated row or None.

        Supports updating status, category_id, claimed_by/claimed_at, and
        close_reason. Only fields present in `data` are changed.
        """
        # Whitelist of columns that may be updated and their incoming keys.
        updatable = (
            "status",
            "category_id",
            "claimed_by",
            "claimed_at",
            "close_reason",
        )
        set_clauses: list[str] = []
        params: list[object | None] = []
        for col in updatable:
            if col in data:
                set_clauses.append(f"{col} = ?")
                params.append(data[col])

        if not set_clauses:
            # Nothing to update; return current row (or None if not found).
            return await self.get_ticket(guild_id, ticket_id)

        params.extend([guild_id, ticket_id])
        async with Database.get_connection() as db:
            cursor = await db.execute(
                f"UPDATE tickets SET {', '.join(set_clauses)} "
                "WHERE guild_id = ? AND id = ?",
                tuple(params),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None

        return await self.get_ticket(guild_id, ticket_id)

    async def close_ticket(
        self, guild_id: int, ticket_id: int, closed_by: int | None = None
    ) -> bool:
        """Set ticket status to 'closed' with closed_at/closed_by. Returns True if updated."""
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE tickets
                SET status = 'closed', closed_at = ?, closed_by = ?
                WHERE guild_id = ? AND id = ? AND status != 'closed'
                """,
                (now, closed_by, guild_id, ticket_id),
            )
            await db.commit()
        return cursor.rowcount > 0
