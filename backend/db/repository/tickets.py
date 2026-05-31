"""TicketRepository — wrapper around Database for ticket queries.

The Database class does not expose dedicated ticket CRUD methods at the time
of writing. This repository issues raw queries via Database.get_connection()
targeting the tickets table (if it exists) or stubs the interface for future use.

TODO: Confirm exact ticket table schema once fully defined in services/db/schema.py.
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
        """Return tickets for a guild, optionally filtered by status.

        TODO: Database class does not yet expose list_tickets(guild_id, status).
        Direct query issued via get_connection().
        """
        async with Database.get_connection() as db:
            if status is not None:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM tickets
                    WHERE guild_id = ?  AND status = ?
                    ORDER BY created_at DESC
                    """,
                    (guild_id, status),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM tickets
                    WHERE guild_id = ?
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

        TODO: Database class does not yet expose create_ticket(guild_id, data).
        """
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO tickets (guild_id, user_id, channel_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    data.get("user_id"),
                    data.get("channel_id"),
                    data.get("status", "open"),
                    now,
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
        """Update mutable fields on a ticket row. Returns updated row or None."""
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE tickets
                SET status = COALESCE(?, status),
                    updated_at = ?
                WHERE guild_id = ? AND id = ?
                """,
                (
                    data.get("status"),
                    now,
                    guild_id,
                    ticket_id,
                ),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None

        return await self.get_ticket(guild_id, ticket_id)

    async def close_ticket(self, guild_id: int, ticket_id: int) -> bool:
        """Set ticket status to 'closed'. Returns True if a row was updated."""
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE tickets
                SET status = 'closed', updated_at = ?
                WHERE guild_id = ? AND id = ? AND status != 'closed'
                """,
                (now, guild_id, ticket_id),
            )
            await db.commit()
        return cursor.rowcount > 0
