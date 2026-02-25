"""
Ticket Service

Business logic for the thread-based ticketing system.
Handles ticket categories, ticket lifecycle, rate-limiting, and statistics.
"""

from __future__ import annotations

import json
import time
from datetime import timezone
from typing import Any

from services.base import BaseService
from services.db.repository import BaseRepository

# Default rate-limit: one ticket per 5 minutes (300 seconds)
TICKET_RATE_LIMIT_SECONDS = 300


class TicketService(BaseService):
    """Service for managing the thread-based ticketing system.

    AI Notes:
        - Categories are per-guild; they populate the dropdown shown to users.
        - Tickets are stored as rows keyed by thread_id (unique).
        - Rate-limiting uses ``created_at`` from the tickets table.
        - Guild-level configuration (channel, panel message, log channel, etc.)
          lives in the ``guild_settings`` table via ``ConfigService``.
    """

    def __init__(self) -> None:
        super().__init__("ticket")

    async def _initialize_impl(self) -> None:
        """No special startup work; DB schema is applied separately."""
        self.logger.info("Ticket service ready")

    # ------------------------------------------------------------------
    # Category CRUD
    # ------------------------------------------------------------------

    async def create_category(
        self,
        guild_id: int,
        name: str,
        description: str = "",
        welcome_message: str = "",
        role_ids: list[int] | None = None,
        emoji: str | None = None,
    ) -> int | None:
        """Create a new ticket category for a guild.

        Args:
            guild_id: Discord guild ID.
            name: Display name for the category.
            description: Short description shown in dropdown.
            welcome_message: Message sent at the start of a new ticket thread.
            role_ids: List of Discord role IDs to add/ping in new tickets.
            emoji: Optional emoji for the dropdown entry.

        Returns:
            The new category row ID, or ``None`` on failure.
        """
        try:
            role_json = json.dumps(role_ids or [])
            # Determine next sort_order
            max_order: int = await BaseRepository.fetch_value(
                "SELECT COALESCE(MAX(sort_order), -1) FROM ticket_categories WHERE guild_id = ?",
                (guild_id,),
                default=-1,
            )
            sort_order = (max_order or 0) + 1

            cat_id = await BaseRepository.insert_returning_id(
                """
                INSERT INTO ticket_categories
                    (guild_id, name, description, welcome_message, role_ids, emoji, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, name, description, welcome_message, role_json, emoji, sort_order),
            )
            self.logger.info(
                "Created ticket category %s (id=%s) for guild %s",
                name,
                cat_id,
                guild_id,
            )
            return cat_id
        except Exception as e:
            self.logger.exception(
                "Failed to create ticket category for guild %s",
                guild_id,
                exc_info=e,
            )
            return None

    async def update_category(
        self,
        category_id: int,
        **kwargs: Any,
    ) -> bool:
        """Update fields on an existing ticket category.

        Accepted keyword arguments: ``name``, ``description``,
        ``welcome_message``, ``role_ids`` (list[int]), ``emoji``,
        ``sort_order``.

        Returns:
            ``True`` if the row was updated.
        """
        allowed = {"name", "description", "welcome_message", "role_ids", "emoji", "sort_order"}
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "role_ids":
                updates[key] = json.dumps(value if value is not None else [])
            else:
                updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), category_id)
        try:
            rows = await BaseRepository.execute(
                f"UPDATE ticket_categories SET {set_clause} WHERE id = ?",  # noqa: S608
                params,
            )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to update ticket category %s",
                category_id,
                exc_info=e,
            )
            return False

    async def delete_category(self, category_id: int) -> bool:
        """Delete a ticket category by ID.

        Returns:
            ``True`` if a row was deleted.
        """
        try:
            rows = await BaseRepository.execute(
                "DELETE FROM ticket_categories WHERE id = ?",
                (category_id,),
            )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to delete ticket category %s",
                category_id,
                exc_info=e,
            )
            return False

    async def get_categories(self, guild_id: int) -> list[dict[str, Any]]:
        """Return all ticket categories for a guild, ordered by ``sort_order``.

        Each dict contains: ``id``, ``guild_id``, ``name``, ``description``,
        ``welcome_message``, ``role_ids`` (list[int]), ``emoji``, ``sort_order``,
        ``created_at``.
        """
        rows = await BaseRepository.fetch_all(
            """
            SELECT id, guild_id, name, description, welcome_message,
                   role_ids, emoji, sort_order, created_at
            FROM ticket_categories
            WHERE guild_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (guild_id,),
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append({
                "id": row[0],
                "guild_id": row[1],
                "name": row[2],
                "description": row[3],
                "welcome_message": row[4],
                "role_ids": json.loads(row[5]) if row[5] else [],
                "emoji": row[6],
                "sort_order": row[7],
                "created_at": row[8],
            })
        return results

    async def get_category(self, category_id: int) -> dict[str, Any] | None:
        """Return a single category by ID, or ``None``."""
        row = await BaseRepository.fetch_one(
            """
            SELECT id, guild_id, name, description, welcome_message,
                   role_ids, emoji, sort_order, created_at
            FROM ticket_categories
            WHERE id = ?
            """,
            (category_id,),
        )
        if row is None:
            return None
        return {
            "id": row[0],
            "guild_id": row[1],
            "name": row[2],
            "description": row[3],
            "welcome_message": row[4],
            "role_ids": json.loads(row[5]) if row[5] else [],
            "emoji": row[6],
            "sort_order": row[7],
            "created_at": row[8],
        }

    # ------------------------------------------------------------------
    # Ticket Lifecycle
    # ------------------------------------------------------------------

    async def create_ticket(
        self,
        guild_id: int,
        channel_id: int,
        thread_id: int,
        user_id: int,
        category_id: int | None = None,
    ) -> int | None:
        """Record a new ticket in the database.

        Args:
            guild_id: Discord guild ID.
            channel_id: Parent text channel ID.
            thread_id: Discord thread ID (unique).
            user_id: ID of the user who opened the ticket.
            category_id: Optional category FK.

        Returns:
            The new ticket row ID, or ``None`` on failure.
        """
        try:
            ticket_id = await BaseRepository.insert_returning_id(
                """
                INSERT INTO tickets (guild_id, channel_id, thread_id, user_id, category_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, thread_id, user_id, category_id),
            )
            self.logger.info(
                "Created ticket %s (thread=%s) for user %s in guild %s",
                ticket_id,
                thread_id,
                user_id,
                guild_id,
            )
            return ticket_id
        except Exception as e:
            self.logger.exception(
                "Failed to create ticket for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )
            return None

    async def close_ticket(self, ticket_id: int, closed_by: int) -> bool:
        """Mark a ticket as closed.

        Args:
            ticket_id: Database row ID of the ticket.
            closed_by: Discord user ID of the person closing the ticket.

        Returns:
            ``True`` if the ticket was updated.
        """
        try:
            now = int(time.time())
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET status = 'closed', closed_by = ?, closed_at = ?
                WHERE id = ? AND status = 'open'
                """,
                (closed_by, now, ticket_id),
            )
            if rows > 0:
                self.logger.info(
                    "Closed ticket %s by user %s", ticket_id, closed_by
                )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to close ticket %s", ticket_id, exc_info=e
            )
            return False

    async def close_ticket_by_thread(self, thread_id: int, closed_by: int) -> bool:
        """Close a ticket identified by its thread ID.

        Returns:
            ``True`` if the ticket was closed.
        """
        try:
            now = int(time.time())
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET status = 'closed', closed_by = ?, closed_at = ?
                WHERE thread_id = ? AND status = 'open'
                """,
                (closed_by, now, thread_id),
            )
            if rows > 0:
                self.logger.info(
                    "Closed ticket (thread=%s) by user %s", thread_id, closed_by
                )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to close ticket by thread %s", thread_id, exc_info=e
            )
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_ticket_by_thread(self, thread_id: int) -> dict[str, Any] | None:
        """Look up a ticket by its Discord thread ID.

        Returns:
            Ticket dict or ``None``.
        """
        row = await BaseRepository.fetch_one(
            """
            SELECT id, guild_id, channel_id, thread_id, user_id,
                   category_id, status, closed_by, created_at, closed_at
            FROM tickets
            WHERE thread_id = ?
            """,
            (thread_id,),
        )
        if row is None:
            return None
        return self._row_to_ticket(row)

    async def get_open_tickets(
        self,
        guild_id: int,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return open tickets, optionally filtered by user.

        Args:
            guild_id: Discord guild ID.
            user_id: If provided, filter to this user's tickets.

        Returns:
            List of ticket dicts.
        """
        if user_id is not None:
            rows = await BaseRepository.fetch_all(
                """
                SELECT id, guild_id, channel_id, thread_id, user_id,
                       category_id, status, closed_by, created_at, closed_at
                FROM tickets
                WHERE guild_id = ? AND user_id = ? AND status = 'open'
                ORDER BY created_at DESC
                """,
                (guild_id, user_id),
            )
        else:
            rows = await BaseRepository.fetch_all(
                """
                SELECT id, guild_id, channel_id, thread_id, user_id,
                       category_id, status, closed_by, created_at, closed_at
                FROM tickets
                WHERE guild_id = ? AND status = 'open'
                ORDER BY created_at DESC
                """,
                (guild_id,),
            )
        return [self._row_to_ticket(r) for r in rows]

    async def get_tickets(
        self,
        guild_id: int,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return tickets with optional status filter and pagination.

        Args:
            guild_id: Discord guild ID.
            status: ``'open'``, ``'closed'``, or ``None`` for all.
            limit: Max rows.
            offset: Row offset for pagination.

        Returns:
            List of ticket dicts.
        """
        if status:
            rows = await BaseRepository.fetch_all(
                """
                SELECT id, guild_id, channel_id, thread_id, user_id,
                       category_id, status, closed_by, created_at, closed_at
                FROM tickets
                WHERE guild_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (guild_id, status, limit, offset),
            )
        else:
            rows = await BaseRepository.fetch_all(
                """
                SELECT id, guild_id, channel_id, thread_id, user_id,
                       category_id, status, closed_by, created_at, closed_at
                FROM tickets
                WHERE guild_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (guild_id, limit, offset),
            )
        return [self._row_to_ticket(r) for r in rows]

    async def get_ticket_count(
        self,
        guild_id: int,
        status: str | None = None,
    ) -> int:
        """Return total ticket count, optionally filtered by status."""
        if status:
            return await BaseRepository.fetch_value(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = ?",
                (guild_id, status),
                default=0,
            )
        return await BaseRepository.fetch_value(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ?",
            (guild_id,),
            default=0,
        )

    async def get_ticket_stats(self, guild_id: int) -> dict[str, int]:
        """Return ticket statistics for a guild.

        Returns:
            Dict with keys ``open``, ``closed``, ``total``.
        """
        open_count: int = await BaseRepository.fetch_value(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'",
            (guild_id,),
            default=0,
        )
        closed_count: int = await BaseRepository.fetch_value(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'closed'",
            (guild_id,),
            default=0,
        )
        return {
            "open": open_count,
            "closed": closed_count,
            "total": open_count + closed_count,
        }

    # ------------------------------------------------------------------
    # Rate Limiting
    # ------------------------------------------------------------------

    async def check_rate_limit(self, guild_id: int, user_id: int) -> bool:
        """Check whether the user can create a new ticket.

        Returns:
            ``True`` if the user is **allowed** (not rate-limited).
            ``False`` if they should wait.
        """
        cutoff = int(time.time()) - TICKET_RATE_LIMIT_SECONDS
        recent = await BaseRepository.exists(
            """
            SELECT 1 FROM tickets
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            """,
            (guild_id, user_id, cutoff),
        )
        return not recent

    async def get_cooldown_remaining(self, guild_id: int, user_id: int) -> int:
        """Return seconds remaining on the rate limit, or 0 if not limited."""
        cutoff = int(time.time()) - TICKET_RATE_LIMIT_SECONDS
        last_created: int | None = await BaseRepository.fetch_value(
            """
            SELECT MAX(created_at) FROM tickets
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            """,
            (guild_id, user_id, cutoff),
        )
        if last_created is None:
            return 0
        remaining = TICKET_RATE_LIMIT_SECONDS - (int(time.time()) - last_created)
        return max(remaining, 0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_ticket(row: Any) -> dict[str, Any]:
        """Convert a database row tuple to a ticket dict."""
        return {
            "id": row[0],
            "guild_id": row[1],
            "channel_id": row[2],
            "thread_id": row[3],
            "user_id": row[4],
            "category_id": row[5],
            "status": row[6],
            "closed_by": row[7],
            "created_at": row[8],
            "closed_at": row[9],
        }
