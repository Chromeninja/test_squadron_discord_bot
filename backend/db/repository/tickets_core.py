"""TicketRepository — core ticket CRUD and cooldown operations.

Issues raw queries via Database.get_connection() against the tickets,
ticket_categories, and ticket_channel_configs tables.
"""

from __future__ import annotations

import json as _json
import time
from typing import Any

from backend.db.repository.tickets_stats import _TicketStatsMixin
from services.db.database import Database


class TicketRepository(_TicketStatsMixin):
    """Core ticket CRUD and cooldown operations.

    All methods require guild_id to scope queries to a single guild.
    """

    async def get_tickets(
        self,
        guild_id: int,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, object | None]]:
        """Return non-deleted tickets for a guild, optionally filtered by status."""
        async with Database.get_connection() as db:
            if status is not None:
                sql = """
                    SELECT *
                    FROM tickets
                    WHERE guild_id = ? AND status = ? AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """
                params: list[object] = [guild_id, status]
            else:
                sql = """
                    SELECT *
                    FROM tickets
                    WHERE guild_id = ? AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """
                params = [guild_id]
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            else:
                sql += " LIMIT -1 OFFSET ?"
                params.append(offset)
            cursor = await db.execute(sql, tuple(params))
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
                "UPDATE tickets SET "
                + ", ".join(set_clauses)
                + " WHERE guild_id = ? AND id = ?",
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

    async def delete_ticket(self, guild_id: int, ticket_id: int) -> bool:
        """Soft-delete a ticket by setting deleted_at. Returns True if a row was updated."""
        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "UPDATE tickets SET deleted_at = ? WHERE guild_id = ? AND id = ? AND deleted_at IS NULL",
                (now, guild_id, ticket_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def claim_ticket(
        self,
        thread_id: int,
        claimed_by: int,
    ) -> bool:
        """Assign a staff member to a ticket.

        Returns:
            True if the ticket was updated.
        """
        try:
            now = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    UPDATE tickets
                    SET claimed_by = ?, claimed_at = ?
                    WHERE thread_id = ? AND status = 'open'
                    """,
                    (claimed_by, now, thread_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def unclaim_ticket(self, thread_id: int) -> bool:
        """Remove the claim from a ticket.

        Returns:
            True if the ticket was updated.
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    UPDATE tickets
                    SET claimed_by = NULL, claimed_at = NULL
                    WHERE thread_id = ? AND status = 'open'
                    """,
                    (thread_id,),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def reopen_ticket(
        self,
        thread_id: int,
        reopened_by: int,
    ) -> bool:
        """Reopen a previously closed ticket.

        Returns:
            True if the ticket was updated.
        """
        try:
            now = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    UPDATE tickets
                    SET status = 'open', reopened_at = ?, reopened_by = ?,
                        closed_by = NULL, closed_at = NULL, close_reason = NULL
                    WHERE thread_id = ? AND status = 'closed'
                    """,
                    (now, reopened_by, thread_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def close_ticket_by_thread(
        self,
        thread_id: int,
        closed_by: int,
        close_reason: str | None = None,
    ) -> bool:
        """Close a ticket identified by its thread ID.

        Returns:
            True if the ticket was closed.
        """
        try:
            now = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    UPDATE tickets
                    SET status = 'closed', closed_by = ?, closed_at = ?,
                        close_reason = ?
                    WHERE thread_id = ? AND status = 'open'
                    """,
                    (closed_by, now, close_reason, thread_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def get_ticket_by_thread(
        self, thread_id: int
    ) -> dict[str, object | None] | None:
        """Look up a ticket by its Discord thread ID.

        Returns:
            Ticket dict or None.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM tickets WHERE thread_id = ?",
                (thread_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def _parse_category_row(self, row: Any) -> dict[str, object | None]:
        """Parse a category row, deserializing JSON role ID fields.

        Returns a dict with role_ids, prerequisite_role_ids_all, and
        prerequisite_role_ids_any as lists (or empty lists on decode error).
        """
        d = dict(row)
        for field in (
            "role_ids",
            "prerequisite_role_ids_all",
            "prerequisite_role_ids_any",
        ):
            raw = d.get(field)
            if isinstance(raw, str):
                try:
                    d[field] = _json.loads(raw)
                except (_json.JSONDecodeError, ValueError):
                    d[field] = []
        return d

    async def create_category(
        self,
        guild_id: int,
        name: str,
        description: str = "",
        welcome_message: str = "",
        role_ids: list[int] | None = None,
        prerequisite_role_ids_all: list[int] | None = None,
        prerequisite_role_ids_any: list[int] | None = None,
        emoji: str | None = None,
        channel_id: int = 0,
    ) -> int | None:
        """Create a new ticket category for a guild.

        Returns:
            The new category row ID, or None on failure.
        """
        try:
            role_json = _json.dumps(role_ids or [])
            prerequisite_role_ids_all_json = _json.dumps(
                prerequisite_role_ids_all or []
            )
            prerequisite_role_ids_any_json = _json.dumps(
                prerequisite_role_ids_any or []
            )

            # Determine next sort_order
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) FROM ticket_categories WHERE guild_id = ?",
                    (guild_id,),
                )
                row = await cursor.fetchone()
                max_order = int(row[0]) if row and row[0] is not None else -1
                sort_order = (max_order or 0) + 1

            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    INSERT INTO ticket_categories
                        (
                            guild_id,
                            channel_id,
                            name,
                            description,
                            welcome_message,
                            role_ids,
                            prerequisite_role_ids_all,
                            prerequisite_role_ids_any,
                            emoji,
                            sort_order
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        channel_id,
                        name,
                        description,
                        welcome_message,
                        role_json,
                        prerequisite_role_ids_all_json,
                        prerequisite_role_ids_any_json,
                        emoji,
                        sort_order,
                    ),
                )
                cat_id = cursor.lastrowid
                await db.commit()
                return int(cat_id) if cat_id else None
        except Exception:
            return None

    async def update_category(
        self,
        category_id: int,
        **kwargs: object,
    ) -> bool:
        """Update fields on an existing ticket category.

        Supports: name, description, welcome_message, role_ids (list[int]),
        prerequisite_role_ids_all (list[int]), prerequisite_role_ids_any
        (list[int]), emoji, sort_order, channel_id.

        Returns:
            True if the row was updated.
        """
        allowed = {
            "name",
            "description",
            "welcome_message",
            "role_ids",
            "prerequisite_role_ids_all",
            "prerequisite_role_ids_any",
            "emoji",
            "sort_order",
            "channel_id",
        }
        updates: dict[str, object] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "role_ids" or key in {
                "prerequisite_role_ids_all",
                "prerequisite_role_ids_any",
            }:
                updates[key] = _json.dumps(value if value is not None else [])
            else:
                updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), category_id)
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "UPDATE ticket_categories SET " + set_clause + " WHERE id = ?",
                    params,
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def delete_category(self, category_id: int) -> bool:
        """Delete a ticket category by ID.

        Returns:
            True if a row was deleted.
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM ticket_categories WHERE id = ?",
                    (category_id,),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def get_categories(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all ticket categories for a guild, ordered by sort_order."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM ticket_categories
                WHERE guild_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
            return [self._parse_category_row(row) for row in rows]

    async def get_category(self, category_id: int) -> dict[str, object | None] | None:
        """Return a single category by ID, or None."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM ticket_categories WHERE id = ?",
                (category_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._parse_category_row(row)

    async def get_categories_for_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> list[dict[str, object | None]]:
        """Return ticket categories assigned to a specific channel."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM ticket_categories
                WHERE guild_id = ? AND channel_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (guild_id, channel_id),
            )
            rows = await cursor.fetchall()
            return [self._parse_category_row(row) for row in rows]

    async def get_channel_configs(
        self, guild_id: int
    ) -> list[dict[str, object | None]]:
        """Return all channel configs for a guild, ordered by sort_order."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM ticket_channel_configs
                WHERE guild_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_channel_config(
        self,
        guild_id: int,
        channel_id: int,
    ) -> dict[str, object | None] | None:
        """Return channel config for a specific channel, or None."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM ticket_channel_configs
                WHERE guild_id = ? AND channel_id = ?
                """,
                (guild_id, channel_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def delete_channel_config(
        self,
        guild_id: int,
        channel_id: int,
    ) -> bool:
        """Delete a channel config.

        Returns:
            True if the config was deleted, False otherwise.
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    DELETE FROM ticket_channel_configs
                    WHERE guild_id = ? AND channel_id = ?
                    """,
                    (guild_id, channel_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def get_ticket_channel_ids(self, guild_id: int) -> list[int]:
        """Return distinct channel IDs that have ticket categories assigned."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT DISTINCT channel_id
                FROM ticket_categories
                WHERE guild_id = ? AND channel_id != 0
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
            result: list[int] = []
            for row in rows:
                try:
                    val = dict(row)["channel_id"] if isinstance(row, tuple) else row[0]
                    result.append(int(val))
                except (TypeError, ValueError, KeyError, IndexError):
                    continue
            return result

    async def reset_user_ticket_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Reset ticket creation cooldown for a specific user (writes a reset marker)."""
        import time as _time

        now = int(_time.time())
        async with Database.get_connection() as db:
            try:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ticket_cooldown_resets (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        reset_at INTEGER NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """
                )
                await db.execute(
                    """
                    INSERT INTO ticket_cooldown_resets (guild_id, user_id, reset_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id)
                    DO UPDATE SET reset_at = excluded.reset_at
                    """,
                    (guild_id, user_id, now),
                )
                await db.commit()
                return True
            except Exception:
                return False

    async def reset_all_ticket_cooldowns(self, guild_id: int) -> bool:
        """Reset ticket cooldown for all users in a guild via sentinel row (user_id=0)."""
        return await self.reset_user_ticket_cooldown(guild_id, 0)
