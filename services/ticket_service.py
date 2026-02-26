"""
Ticket Service

Business logic for the thread-based ticketing system.
Handles ticket categories, ticket lifecycle, rate-limiting, claiming,
reopening, transcripts, and statistics.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from services.base import BaseService
from services.db.repository import BaseRepository

# Default rate-limit: one ticket per 5 minutes (300 seconds)
TICKET_RATE_LIMIT_SECONDS = 300

# Default max open tickets per user per guild
DEFAULT_MAX_OPEN_PER_USER = 5

# Default reopen window in hours
DEFAULT_REOPEN_WINDOW_HOURS = 48

# Special user_id used for guild-wide cooldown reset markers.
_GLOBAL_COOLDOWN_RESET_USER_ID = 0

# Column names for ticket SELECT queries — keep in sync with _row_to_ticket()
_TICKET_COLUMN_NAMES = [
    "id", "guild_id", "channel_id", "thread_id", "user_id",
    "category_id", "status", "closed_by", "created_at", "closed_at",
    "claimed_by", "claimed_at", "close_reason", "initial_description",
    "reopened_at", "reopened_by",
]
_TICKET_COLUMNS = ", ".join(_TICKET_COLUMN_NAMES)

# Column names for category SELECT queries — keep in sync with _row_to_category()
_CATEGORY_COLUMN_NAMES = [
    "id", "guild_id", "name", "description", "welcome_message",
    "role_ids", "allowed_statuses", "emoji", "sort_order", "created_at",
]
_CATEGORY_COLUMNS = ", ".join(_CATEGORY_COLUMN_NAMES)

_ALLOWED_CATEGORY_STATUS_VALUES = {
    "bot_verified",
    "org_main",
    "org_affiliate",
}


class TicketService(BaseService):
    """Service for managing the thread-based ticketing system.

    AI Notes:
        - Categories are per-guild; they populate the dropdown shown to users.
        - Tickets are stored as rows keyed by thread_id (unique).
        - Rate-limiting uses ``created_at`` from the tickets table.
        - Guild-level configuration (channel, panel message, log channel, etc.)
          lives in the ``guild_settings`` table via ``ConfigService``.
        - Staff role IDs are stored as a JSON array string in
          ``guild_settings`` under key ``tickets.staff_roles``.
        - ``get_staff_role_ids()`` is the single source of truth for parsing
          staff roles — all call-sites should use it instead of inlining
          the JSON parsing logic.
    """

    def __init__(self) -> None:
        super().__init__("ticket")
        self._category_schema_checked = False

    async def _initialize_impl(self) -> None:
        """No special startup work; DB schema is applied separately."""
        self.logger.info("Ticket service ready")

    # ------------------------------------------------------------------
    # Staff roles (DRY — single source of truth)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_staff_role_ids(
        config_service: Any,
        guild_id: int,
    ) -> list[int]:
        """Return the configured staff role IDs for a guild.

        Parses the JSON array stored in ``tickets.staff_roles`` via
        ``ConfigService``.  All call-sites that need staff roles should
        use this method rather than duplicating the JSON parsing.

        Args:
            config_service: ``ConfigService`` instance (passed to avoid
                circular imports — the service layer doesn't depend on
                the bot or config service directly).
            guild_id: Discord guild ID.

        Returns:
            List of Discord role ID integers.
        """
        raw = await config_service.get_guild_setting(
            guild_id, "tickets.staff_roles", default="[]"
        )
        try:
            parsed: Any = raw
            # Handle values that may be JSON encoded more than once,
            # e.g. '"[123,456]"' from historical config writes.
            for _ in range(2):
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                    continue
                break
            if parsed is None:
                parsed = []
            return [int(r) for r in parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

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
        allowed_statuses: list[str] | None = None,
        emoji: str | None = None,
    ) -> int | None:
        """Create a new ticket category for a guild.

        Args:
            guild_id: Discord guild ID.
            name: Display name for the category.
            description: Short description shown in dropdown.
            welcome_message: Message sent at the start of a new ticket thread.
            role_ids: List of Discord role IDs to add/ping in new tickets.
            allowed_statuses: Optional eligibility statuses that can open this
                category. Allowed values: ``bot_verified``, ``org_main``,
                ``org_affiliate``. Empty means unrestricted.
            emoji: Optional emoji for the dropdown entry.

        Returns:
            The new category row ID, or ``None`` on failure.
        """
        try:
            await self._ensure_category_schema_compatibility()
            role_json = json.dumps(role_ids or [])
            allowed_statuses_json = json.dumps(
                self._normalize_allowed_statuses(allowed_statuses)
            )
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
                    (
                        guild_id,
                        name,
                        description,
                        welcome_message,
                        role_ids,
                        allowed_statuses,
                        emoji,
                        sort_order
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    name,
                    description,
                    welcome_message,
                    role_json,
                    allowed_statuses_json,
                    emoji,
                    sort_order,
                ),
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
        ``welcome_message``, ``role_ids`` (list[int]),
        ``allowed_statuses`` (list[str]), ``emoji``,
        ``sort_order``.

        Returns:
            ``True`` if the row was updated.
        """
        await self._ensure_category_schema_compatibility()
        allowed = {
            "name",
            "description",
            "welcome_message",
            "role_ids",
            "allowed_statuses",
            "emoji",
            "sort_order",
        }
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "role_ids":
                updates[key] = json.dumps(value if value is not None else [])
            elif key == "allowed_statuses":
                updates[key] = json.dumps(self._normalize_allowed_statuses(value))
            else:
                updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), category_id)
        try:
            rows = await BaseRepository.execute(
                f"UPDATE ticket_categories SET {set_clause} WHERE id = ?",
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
        ``welcome_message``, ``role_ids`` (list[int]),
        ``allowed_statuses`` (list[str]), ``emoji``, ``sort_order``,
        ``created_at``.
        """
        await self._ensure_category_schema_compatibility()
        rows = await BaseRepository.fetch_all(
            f"""
            SELECT {_CATEGORY_COLUMNS}
            FROM ticket_categories
            WHERE guild_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (guild_id,),
        )
        return [self._row_to_category(r) for r in rows]

    async def get_category(self, category_id: int) -> dict[str, Any] | None:
        """Return a single category by ID, or ``None``."""
        await self._ensure_category_schema_compatibility()
        row = await BaseRepository.fetch_one(
            f"""
            SELECT {_CATEGORY_COLUMNS}
            FROM ticket_categories
            WHERE id = ?
            """,
            (category_id,),
        )
        if row is None:
            return None
        return self._row_to_category(row)

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
        initial_description: str | None = None,
    ) -> int | None:
        """Record a new ticket in the database.

        Args:
            guild_id: Discord guild ID.
            channel_id: Parent text channel ID.
            thread_id: Discord thread ID (unique).
            user_id: ID of the user who opened the ticket.
            category_id: Optional category FK.
            initial_description: User-provided description from the modal.

        Returns:
            The new ticket row ID, or ``None`` on failure.
        """
        try:
            ticket_id = await BaseRepository.insert_returning_id(
                """
                INSERT INTO tickets
                    (guild_id, channel_id, thread_id, user_id, category_id, initial_description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, thread_id, user_id, category_id, initial_description),
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

    async def close_ticket(
        self,
        ticket_id: int,
        closed_by: int,
        close_reason: str | None = None,
    ) -> bool:
        """Mark a ticket as closed.

        Args:
            ticket_id: Database row ID of the ticket.
            closed_by: Discord user ID of the person closing the ticket.
            close_reason: Optional reason provided via the close modal.

        Returns:
            ``True`` if the ticket was updated.
        """
        try:
            now = int(time.time())
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET status = 'closed', closed_by = ?, closed_at = ?,
                    close_reason = ?
                WHERE id = ? AND status = 'open'
                """,
                (closed_by, now, close_reason, ticket_id),
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

    async def close_ticket_by_thread(
        self,
        thread_id: int,
        closed_by: int,
        close_reason: str | None = None,
    ) -> bool:
        """Close a ticket identified by its thread ID.

        Args:
            thread_id: Discord thread ID.
            closed_by: Discord user ID of the person closing the ticket.
            close_reason: Optional reason provided via the close modal.

        Returns:
            ``True`` if the ticket was closed.
        """
        try:
            now = int(time.time())
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET status = 'closed', closed_by = ?, closed_at = ?,
                    close_reason = ?
                WHERE thread_id = ? AND status = 'open'
                """,
                (closed_by, now, close_reason, thread_id),
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
            f"""
            SELECT {_TICKET_COLUMNS}
            FROM tickets
            WHERE thread_id = ?
            """,
            (thread_id,),
        )
        if row is None:
            return None
        return self._row_to_ticket(row)

    async def get_ticket_by_id(
        self, ticket_id: int, guild_id: int | None = None
    ) -> dict[str, Any] | None:
        """Look up a ticket by its row ID, optionally scoped to a guild.

        Args:
            ticket_id: Database row ID.
            guild_id: If provided, the ticket must belong to this guild.

        Returns:
            Ticket dict or ``None``.
        """
        where = "WHERE id = ?"
        params: list[Any] = [ticket_id]
        if guild_id is not None:
            where += " AND guild_id = ?"
            params.append(guild_id)
        row = await BaseRepository.fetch_one(
            f"SELECT {_TICKET_COLUMNS} FROM tickets {where}", tuple(params)
        )
        return self._row_to_ticket(row) if row else None

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
        where = "WHERE guild_id = ? AND status = 'open'"
        params: list[Any] = [guild_id]
        if user_id is not None:
            where += " AND user_id = ?"
            params.append(user_id)
        rows = await BaseRepository.fetch_all(
            f"SELECT {_TICKET_COLUMNS} FROM tickets {where} ORDER BY created_at DESC",
            tuple(params),
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
        where = "WHERE guild_id = ?"
        params: list[Any] = [guild_id]
        if status:
            where += " AND status = ?"
            params.append(status)
        params.extend([limit, offset])
        rows = await BaseRepository.fetch_all(
            f"SELECT {_TICKET_COLUMNS} FROM tickets {where} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
        return [self._row_to_ticket(r) for r in rows]

    async def get_ticket_count(
        self,
        guild_id: int,
        status: str | None = None,
    ) -> int:
        """Return total ticket count, optionally filtered by status."""
        where = "WHERE guild_id = ?"
        params: list[Any] = [guild_id]
        if status:
            where += " AND status = ?"
            params.append(status)
        return await BaseRepository.fetch_value(
            f"SELECT COUNT(*) FROM tickets {where}",
            tuple(params),
            default=0,
        )

    async def get_ticket_stats(self, guild_id: int) -> dict[str, int]:
        """Return ticket statistics for a guild.

        Uses a single ``GROUP BY`` query for efficiency.

        Returns:
            Dict with keys ``open``, ``closed``, ``total``.
        """
        rows = await BaseRepository.fetch_all(
            "SELECT status, COUNT(*) AS cnt FROM tickets "
            "WHERE guild_id = ? GROUP BY status",
            (guild_id,),
        )
        counts: dict[str, int] = {"open": 0, "closed": 0}
        for row in rows:
            status = row["status"] if isinstance(row, dict) else row[0]
            cnt = row["cnt"] if isinstance(row, dict) else row[1]
            if status in counts:
                counts[status] = int(cnt)
        return {
            "open": counts["open"],
            "closed": counts["closed"],
            "total": counts["open"] + counts["closed"],
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
        floor = await self._get_cooldown_floor(guild_id, user_id, cutoff)
        recent = await BaseRepository.exists(
            """
            SELECT 1 FROM tickets
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            """,
            (guild_id, user_id, floor),
        )
        return not recent

    async def get_cooldown_remaining(self, guild_id: int, user_id: int) -> int:
        """Return seconds remaining on the rate limit, or 0 if not limited."""
        cutoff = int(time.time()) - TICKET_RATE_LIMIT_SECONDS
        floor = await self._get_cooldown_floor(guild_id, user_id, cutoff)
        last_created: int | None = await BaseRepository.fetch_value(
            """
            SELECT MAX(created_at) FROM tickets
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            """,
            (guild_id, user_id, floor),
        )
        if last_created is None:
            return 0
        remaining = TICKET_RATE_LIMIT_SECONDS - (int(time.time()) - last_created)
        return max(remaining, 0)

    async def reset_user_ticket_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Reset ticket cooldown timer for a specific user in a guild."""
        now = int(time.time())
        try:
            await self._ensure_cooldown_reset_table()
            await BaseRepository.execute(
                """
                INSERT INTO ticket_cooldown_resets (guild_id, user_id, reset_at)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET reset_at = excluded.reset_at
                """,
                (guild_id, user_id, now),
            )
            return True
        except Exception as e:
            self.logger.exception(
                "Failed to reset ticket cooldown for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )
            return False

    async def reset_all_ticket_cooldowns(self, guild_id: int) -> bool:
        """Reset ticket cooldown timer for all users in a guild."""
        return await self.reset_user_ticket_cooldown(
            guild_id,
            _GLOBAL_COOLDOWN_RESET_USER_ID,
        )

    async def _ensure_cooldown_reset_table(self) -> None:
        """Ensure storage for cooldown reset markers exists."""
        await BaseRepository.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_cooldown_resets (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reset_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

    async def _get_cooldown_floor(
        self,
        guild_id: int,
        user_id: int,
        cutoff: int,
    ) -> int:
        """Return effective cutoff considering manual cooldown resets."""
        try:
            reset_at: int | None = await BaseRepository.fetch_value(
                """
                SELECT MAX(reset_at) FROM ticket_cooldown_resets
                WHERE guild_id = ? AND user_id IN (?, ?)
                """,
                (guild_id, _GLOBAL_COOLDOWN_RESET_USER_ID, user_id),
            )
        except Exception:
            return cutoff

        if reset_at is None:
            return cutoff
        return max(cutoff, int(reset_at))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: Any, columns: list[str]) -> dict[str, Any]:
        """Convert a database row to a dict.

        Supports dict-like ``aiosqlite.Row`` (preferred) and plain
        tuples (legacy fallback using *columns* for key mapping).
        Missing keys are filled with ``None``.
        """
        try:
            d = dict(row)
        except (TypeError, ValueError):
            d = dict(zip(columns, row, strict=False))
        # Ensure every expected column is present (handles short tuples)
        for col in columns:
            d.setdefault(col, None)
        return d

    @staticmethod
    def _row_to_ticket(row: Any) -> dict[str, Any]:
        """Convert a database row to a ticket dict."""
        return TicketService._row_to_dict(row, _TICKET_COLUMN_NAMES)

    @staticmethod
    def _row_to_category(row: Any) -> dict[str, Any]:
        """Convert a database row to a category dict."""
        d = TicketService._row_to_dict(row, _CATEGORY_COLUMN_NAMES)
        role_ids_raw = d.get("role_ids")
        try:
            d["role_ids"] = json.loads(role_ids_raw) if role_ids_raw else []
        except (TypeError, ValueError, json.JSONDecodeError):
            d["role_ids"] = []

        d["allowed_statuses"] = TicketService._normalize_allowed_statuses(
            d.get("allowed_statuses")
        )
        return d

    @staticmethod
    def _normalize_allowed_statuses(raw: Any) -> list[str]:
        """Normalize stored category eligibility statuses."""
        if raw is None:
            return []

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return []
        elif isinstance(raw, list):
            parsed = raw
        else:
            return []

        normalized: list[str] = []
        for item in parsed:
            if not isinstance(item, str):
                continue
            value = item.strip().lower()
            if value not in _ALLOWED_CATEGORY_STATUS_VALUES:
                continue
            if value in normalized:
                continue
            normalized.append(value)

        return normalized

    async def _ensure_category_schema_compatibility(self) -> None:
        """Ensure ticket category eligibility columns exist on older DBs."""
        if self._category_schema_checked:
            return

        rows = await BaseRepository.fetch_all("PRAGMA table_info(ticket_categories)")
        column_names: set[str] = set()
        for row in rows:
            try:
                column_name = str(row["name"])
            except (TypeError, KeyError, IndexError):
                column_name = str(row[1]) if len(row) > 1 else ""
            if column_name:
                column_names.add(column_name)

        if "allowed_statuses" not in column_names:
            try:
                await BaseRepository.execute(
                    "ALTER TABLE ticket_categories "
                    "ADD COLUMN allowed_statuses TEXT NOT NULL DEFAULT '[]'"
                )
                self.logger.info(
                    "Added missing allowed_statuses column to ticket_categories"
                )
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise

        self._category_schema_checked = True

    # ------------------------------------------------------------------
    # Claim / Assign
    # ------------------------------------------------------------------

    async def claim_ticket(
        self,
        thread_id: int,
        claimed_by: int,
    ) -> bool:
        """Assign a staff member to a ticket.

        Args:
            thread_id: Discord thread ID.
            claimed_by: Discord user ID of the staff member claiming.

        Returns:
            ``True`` if the ticket was updated.
        """
        try:
            now = int(time.time())
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET claimed_by = ?, claimed_at = ?
                WHERE thread_id = ? AND status = 'open'
                """,
                (claimed_by, now, thread_id),
            )
            if rows > 0:
                self.logger.info(
                    "Ticket (thread=%s) claimed by user %s",
                    thread_id,
                    claimed_by,
                )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to claim ticket (thread=%s)",
                thread_id,
                exc_info=e,
            )
            return False

    async def unclaim_ticket(self, thread_id: int) -> bool:
        """Remove the claim from a ticket.

        Returns:
            ``True`` if the ticket was updated.
        """
        try:
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET claimed_by = NULL, claimed_at = NULL
                WHERE thread_id = ? AND status = 'open'
                """,
                (thread_id,),
            )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to unclaim ticket (thread=%s)",
                thread_id,
                exc_info=e,
            )
            return False

    # ------------------------------------------------------------------
    # Reopen
    # ------------------------------------------------------------------

    async def reopen_ticket(
        self,
        thread_id: int,
        reopened_by: int,
    ) -> bool:
        """Reopen a previously closed ticket.

        Args:
            thread_id: Discord thread ID.
            reopened_by: Discord user ID of the person reopening.

        Returns:
            ``True`` if the ticket was updated.
        """
        try:
            now = int(time.time())
            rows = await BaseRepository.execute(
                """
                UPDATE tickets
                SET status = 'open', reopened_at = ?, reopened_by = ?,
                    closed_by = NULL, closed_at = NULL, close_reason = NULL
                WHERE thread_id = ? AND status = 'closed'
                """,
                (now, reopened_by, thread_id),
            )
            if rows > 0:
                self.logger.info(
                    "Reopened ticket (thread=%s) by user %s",
                    thread_id,
                    reopened_by,
                )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to reopen ticket (thread=%s)",
                thread_id,
                exc_info=e,
            )
            return False

    async def can_reopen(
        self,
        thread_id: int,
        reopen_window_hours: int = DEFAULT_REOPEN_WINDOW_HOURS,
    ) -> bool:
        """Check whether a closed ticket is still within the reopen window.

        Args:
            thread_id: Discord thread ID.
            reopen_window_hours: Hours after closure during which reopen is allowed.

        Returns:
            ``True`` if the ticket exists, is closed, and within the window.
        """
        cutoff = int(time.time()) - (reopen_window_hours * 3600)
        return await BaseRepository.exists(
            """
            SELECT 1 FROM tickets
            WHERE thread_id = ? AND status = 'closed' AND closed_at > ?
            """,
            (thread_id, cutoff),
        )

    # ------------------------------------------------------------------
    # Max Open Tickets
    # ------------------------------------------------------------------

    async def get_open_ticket_count(
        self,
        guild_id: int,
        user_id: int,
    ) -> int:
        """Return the number of currently open tickets for a user in a guild."""
        count: int = await BaseRepository.fetch_value(
            """
            SELECT COUNT(*) FROM tickets
            WHERE guild_id = ? AND user_id = ? AND status = 'open'
            """,
            (guild_id, user_id),
            default=0,
        )
        return count

    async def check_max_open_tickets(
        self,
        guild_id: int,
        user_id: int,
        max_open: int = DEFAULT_MAX_OPEN_PER_USER,
    ) -> bool:
        """Check whether the user is below the max open ticket limit.

        Args:
            guild_id: Discord guild ID.
            user_id: Discord user ID.
            max_open: Maximum allowed open tickets per user.

        Returns:
            ``True`` if the user can open another ticket.
        """
        current = await self.get_open_ticket_count(guild_id, user_id)
        return current < max_open
