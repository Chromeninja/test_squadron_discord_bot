"""
Ticket Service

Business logic for the thread-based ticketing system.
Handles ticket categories, ticket lifecycle, rate-limiting, claiming,
reopening, transcripts, and statistics.
"""

from __future__ import annotations

import asyncio
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

# Default thread limit used for health-percentage calculations.
# Discord's actual per-guild active thread cap varies by boost level
# (default ~500 active).  This value is a conservative upper bound
# representing total tracked ticket threads (active + archived).
DEFAULT_THREAD_LIMIT = 1000

# Special user_id used for guild-wide cooldown reset markers.
_GLOBAL_COOLDOWN_RESET_USER_ID = 0

# Column names for ticket SELECT queries — keep in sync with _row_to_ticket()
_TICKET_COLUMN_NAMES = [
    "id", "guild_id", "channel_id", "thread_id", "user_id",
    "category_id", "status", "closed_by", "created_at", "closed_at",
    "claimed_by", "claimed_at", "close_reason", "initial_description",
    "reopened_at", "reopened_by", "deleted_at",
]
_TICKET_COLUMNS = ", ".join(_TICKET_COLUMN_NAMES)

# Column names for category SELECT queries — keep in sync with _row_to_category()
_CATEGORY_COLUMN_NAMES = [
    "id", "guild_id", "channel_id", "name", "description", "welcome_message",
    "role_ids", "prerequisite_role_ids_all", "prerequisite_role_ids_any",
    "emoji", "sort_order", "created_at",
]
_CATEGORY_COLUMNS = ", ".join(_CATEGORY_COLUMN_NAMES)

# Column names for channel config SELECT queries — keep in sync with _row_to_channel_config()
_CHANNEL_CONFIG_COLUMN_NAMES = [
    "id", "guild_id", "channel_id", "panel_title", "panel_description",
    "panel_color", "button_text", "button_emoji", "enable_public_button",
    "public_button_text", "public_button_emoji", "private_button_color",
    "public_button_color", "button_order", "sort_order", "created_at",
]
_CHANNEL_CONFIG_COLUMNS = ", ".join(_CHANNEL_CONFIG_COLUMN_NAMES)

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
        self._ticket_schema_checked = False
        self._channel_config_schema_checked = False
        self._schema_lock = asyncio.Lock()

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
        prerequisite_role_ids_all: list[int] | None = None,
        prerequisite_role_ids_any: list[int] | None = None,
        emoji: str | None = None,
        channel_id: int = 0,
    ) -> int | None:
        """Create a new ticket category for a guild.

        Args:
            guild_id: Discord guild ID.
            name: Display name for the category.
            description: Short description shown in dropdown.
            welcome_message: Message sent at the start of a new ticket thread.
            role_ids: List of Discord role IDs to add/ping in new tickets.
            prerequisite_role_ids_all: Role IDs the member must all have to
                create a ticket in this category.
            prerequisite_role_ids_any: Role IDs where the member must have at
                least one to create a ticket in this category.
            emoji: Optional emoji for the dropdown entry.
            channel_id: Discord channel ID where this category's panel lives.

        Returns:
            The new category row ID, or ``None`` on failure.
        """
        try:
            await self._ensure_category_schema_compatibility()
            role_json = json.dumps(role_ids or [])
            prerequisite_role_ids_all_json = json.dumps(
                self._normalize_role_id_list(prerequisite_role_ids_all)
            )
            prerequisite_role_ids_any_json = json.dumps(
                self._normalize_role_id_list(prerequisite_role_ids_any)
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
            self.logger.info(
                "Created ticket category %s (id=%s) for guild %s channel %s",
                name,
                cat_id,
                guild_id,
                channel_id,
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
        ``prerequisite_role_ids_all`` (list[int]),
        ``prerequisite_role_ids_any`` (list[int]), ``emoji``,
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
            "prerequisite_role_ids_all",
            "prerequisite_role_ids_any",
            "emoji",
            "sort_order",
            "channel_id",
        }
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "role_ids":
                updates[key] = json.dumps(value if value is not None else [])
            elif key in {"prerequisite_role_ids_all", "prerequisite_role_ids_any"}:
                updates[key] = json.dumps(self._normalize_role_id_list(value))
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
        ``prerequisite_role_ids_all`` (list[int]),
        ``prerequisite_role_ids_any`` (list[int]), ``emoji``, ``sort_order``,
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

    async def get_categories_for_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> list[dict[str, Any]]:
        """Return ticket categories assigned to a specific channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Discord text channel ID.

        Returns:
            List of category dicts for the given channel, ordered by
            ``sort_order``.
        """
        await self._ensure_category_schema_compatibility()
        rows = await BaseRepository.fetch_all(
            f"""
            SELECT {_CATEGORY_COLUMNS}
            FROM ticket_categories
            WHERE guild_id = ? AND channel_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (guild_id, channel_id),
        )
        return [self._row_to_category(r) for r in rows]

    async def get_ticket_channel_ids(self, guild_id: int) -> list[int]:
        """Return distinct channel IDs that have ticket categories assigned.

        Args:
            guild_id: Discord guild ID.

        Returns:
            List of unique channel ID integers (excluding 0/unassigned).
        """
        await self._ensure_category_schema_compatibility()
        rows = await BaseRepository.fetch_all(
            """
            SELECT DISTINCT channel_id
            FROM ticket_categories
            WHERE guild_id = ? AND channel_id != 0
            """,
            (guild_id,),
        )
        result: list[int] = []
        for row in rows:
            try:
                val = row["channel_id"] if isinstance(row, dict) else row[0]
                result.append(int(val))
            except (TypeError, ValueError, KeyError, IndexError):
                continue
        return result

    # ------------------------------------------------------------------
    # Channel Configs (per-channel panel customization)
    # ------------------------------------------------------------------

    async def get_channel_configs(self, guild_id: int) -> list[dict[str, Any]]:
        """Return all channel configs for a guild, ordered by sort_order.

        Each dict contains: ``id``, ``guild_id``, ``channel_id``,
        ``panel_title``, ``panel_description``, ``panel_color``,
        ``button_text``, ``button_emoji``, ``enable_public_button``,
        ``public_button_text``, ``public_button_emoji``,
        ``private_button_color``, ``public_button_color``, ``button_order``,
        ``sort_order``, ``created_at``.
        """
        await self._ensure_channel_config_schema_compatibility()
        rows = await BaseRepository.fetch_all(
            f"""
            SELECT {_CHANNEL_CONFIG_COLUMNS}
            FROM ticket_channel_configs
            WHERE guild_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (guild_id,),
        )
        return [self._row_to_channel_config(r) for r in rows]

    async def get_channel_config(
        self,
        guild_id: int,
        channel_id: int,
    ) -> dict[str, Any] | None:
        """Return channel config for a specific channel, or None."""
        await self._ensure_channel_config_schema_compatibility()
        row = await BaseRepository.fetch_one(
            f"""
            SELECT {_CHANNEL_CONFIG_COLUMNS}
            FROM ticket_channel_configs
            WHERE guild_id = ? AND channel_id = ?
            """,
            (guild_id, channel_id),
        )
        if row is None:
            return None
        return self._row_to_channel_config(row)

    async def create_channel_config(
        self,
        guild_id: int,
        channel_id: int,
        panel_title: str | None = None,
        panel_description: str | None = None,
        panel_color: str | None = None,
        button_text: str | None = None,
        button_emoji: str | None = None,
        enable_public_button: bool | None = None,
        public_button_text: str | None = None,
        public_button_emoji: str | None = None,
        private_button_color: str | None = None,
        public_button_color: str | None = None,
        button_order: str | None = None,
    ) -> int | None:
        """Create a new channel config with customized panel settings.

        Args:
            guild_id: Discord guild ID.
            channel_id: Discord text channel ID.
            panel_title: Optional custom title (uses default if None).
            panel_description: Optional custom description (uses default if None).
            panel_color: Optional hex color (uses default if None).
            button_text: Optional button text (uses default if None).
            button_emoji: Optional button emoji (uses default if None).
            enable_public_button: Optional public-button toggle.
            public_button_text: Optional public-button label.
            public_button_emoji: Optional public-button emoji.
            private_button_color: Optional hex color for private button.
            public_button_color: Optional hex color for public button.
            button_order: Order of buttons ('private_first' or 'public_first').

        Returns:
            The new channel config row ID, or None on failure.
        """
        try:
            await self._ensure_channel_config_schema_compatibility()
            # Build SQL with optional columns
            cols = ["guild_id", "channel_id"]
            vals: list[Any] = [guild_id, channel_id]

            if panel_title is not None:
                cols.append("panel_title")
                vals.append(panel_title)
            if panel_description is not None:
                cols.append("panel_description")
                vals.append(panel_description)
            if panel_color is not None:
                cols.append("panel_color")
                vals.append(panel_color)
            if button_text is not None:
                cols.append("button_text")
                vals.append(button_text)
            if button_emoji is not None:
                cols.append("button_emoji")
                vals.append(button_emoji)
            if enable_public_button is not None:
                cols.append("enable_public_button")
                vals.append(1 if enable_public_button else 0)
            if public_button_text is not None:
                cols.append("public_button_text")
                vals.append(public_button_text)
            if public_button_emoji is not None:
                cols.append("public_button_emoji")
                vals.append(public_button_emoji)
            if private_button_color is not None:
                cols.append("private_button_color")
                vals.append(private_button_color)
            if public_button_color is not None:
                cols.append("public_button_color")
                vals.append(public_button_color)
            if button_order is not None:
                cols.append("button_order")
                vals.append(button_order)

            placeholders = ", ".join("?" * len(vals))
            col_names = ", ".join(cols)

            config_id = await BaseRepository.insert_returning_id(
                f"""
                INSERT INTO ticket_channel_configs ({col_names})
                VALUES ({placeholders})
                """,
                tuple(vals),
            )
            self.logger.info(
                "Created channel config %s for guild %s channel %s",
                config_id,
                guild_id,
                channel_id,
            )
            return config_id
        except Exception as e:
            self.logger.exception(
                "Failed to create channel config for guild %s channel %s",
                guild_id,
                channel_id,
                exc_info=e,
            )
            return None

    async def update_channel_config(
        self,
        guild_id: int,
        channel_id: int,
        new_channel_id: int | None = None,
        panel_title: str | None = None,
        panel_description: str | None = None,
        panel_color: str | None = None,
        button_text: str | None = None,
        button_emoji: str | None = None,
        enable_public_button: bool | None = None,
        public_button_text: str | None = None,
        public_button_emoji: str | None = None,
        private_button_color: str | None = None,
        public_button_color: str | None = None,
        button_order: str | None = None,
    ) -> bool:
        """Update an existing channel config.

        Args:
            guild_id: Discord guild ID.
            channel_id: Current Discord channel ID.
            new_channel_id: New Discord channel ID (to move the config).
            panel_title: New panel title (unchanged if None).
            panel_description: New panel description (unchanged if None).
            panel_color: New panel color (unchanged if None).
            button_text: New button text (unchanged if None).
            button_emoji: New button emoji (unchanged if None).
            enable_public_button: Enable public button when true.
            public_button_text: New public button text.
            public_button_emoji: New public button emoji.
            private_button_color: Private button color (hex).
            public_button_color: Public button color (hex).
            button_order: Button display order.

        Returns:
            True if the config was updated, False otherwise.

        Raises:
            ValueError: If new_channel_id is provided but already has a config.
        """
        try:
            await self._ensure_channel_config_schema_compatibility()

            # Validate new channel_id doesn't conflict
            if new_channel_id is not None and new_channel_id != channel_id:
                existing = await self.get_channel_config(guild_id, new_channel_id)
                if existing:
                    raise ValueError(
                        f"Channel {new_channel_id} already has a ticket panel configuration"
                    )

            updates: list[str] = []
            vals: list[Any] = []

            if new_channel_id is not None and new_channel_id != channel_id:
                updates.append("channel_id = ?")
                vals.append(new_channel_id)

            if panel_title is not None:
                updates.append("panel_title = ?")
                vals.append(panel_title)
            if panel_description is not None:
                updates.append("panel_description = ?")
                vals.append(panel_description)
            if panel_color is not None:
                updates.append("panel_color = ?")
                vals.append(panel_color)
            if button_text is not None:
                updates.append("button_text = ?")
                vals.append(button_text)
            if button_emoji is not None:
                updates.append("button_emoji = ?")
                vals.append(button_emoji)
            if enable_public_button is not None:
                updates.append("enable_public_button = ?")
                vals.append(1 if enable_public_button else 0)
            if public_button_text is not None:
                updates.append("public_button_text = ?")
                vals.append(public_button_text)
            if public_button_emoji is not None:
                updates.append("public_button_emoji = ?")
                vals.append(public_button_emoji)
            if private_button_color is not None:
                updates.append("private_button_color = ?")
                vals.append(private_button_color)
            if public_button_color is not None:
                updates.append("public_button_color = ?")
                vals.append(public_button_color)
            if button_order is not None:
                updates.append("button_order = ?")
                vals.append(button_order)

            if not updates:
                return False  # Nothing to update

            vals.append(guild_id)
            vals.append(channel_id)

            rows = await BaseRepository.execute(
                f"""
                UPDATE ticket_channel_configs
                SET {", ".join(updates)}
                WHERE guild_id = ? AND channel_id = ?
                """,
                tuple(vals),
            )

            if rows > 0:
                # If channel_id changed, update categories assigned to this channel
                if new_channel_id is not None and new_channel_id != channel_id:
                    await BaseRepository.execute(
                        """
                        UPDATE ticket_categories
                        SET channel_id = ?
                        WHERE guild_id = ? AND channel_id = ?
                        """,
                        (new_channel_id, guild_id, channel_id),
                    )
                    self.logger.info(
                        "Moved channel config from %s to %s for guild %s",
                        channel_id,
                        new_channel_id,
                        guild_id,
                    )
                else:
                    self.logger.info(
                        "Updated channel config for guild %s channel %s",
                        guild_id,
                        channel_id,
                    )
            return rows > 0
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            self.logger.exception(
                "Failed to update channel config for guild %s channel %s",
                guild_id,
                channel_id,
                exc_info=e,
            )
            return False

    async def delete_channel_config(
        self,
        guild_id: int,
        channel_id: int,
    ) -> bool:
        """Delete a channel config.

        AI Notes:
            This does NOT delete the categories assigned to the channel.
            Those will become "unassigned" (channel_id = 0) and should be
            handled by the caller.

        Args:
            guild_id: Discord guild ID.
            channel_id: Discord channel ID.

        Returns:
            True if the config was deleted, False otherwise.
        """
        try:
            rows = await BaseRepository.execute(
                """
                DELETE FROM ticket_channel_configs
                WHERE guild_id = ? AND channel_id = ?
                """,
                (guild_id, channel_id),
            )
            if rows > 0:
                self.logger.info(
                    "Deleted channel config for guild %s channel %s",
                    guild_id,
                    channel_id,
                )
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to delete channel config for guild %s channel %s",
                guild_id,
                channel_id,
                exc_info=e,
            )
            return False

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

    async def get_thread_health(
        self,
        guild_id: int,
        thread_limit: int = DEFAULT_THREAD_LIMIT,
    ) -> dict[str, Any]:
        """Return thread usage data for a guild.

        Args:
            guild_id: Discord guild ID.
            thread_limit: Maximum thread count used for usage-percentage
                calculations.  Defaults to ``DEFAULT_THREAD_LIMIT``.

        Returns a dict with:
            ``active`` — open ticket count (threads still active).
            ``archived`` — closed tickets whose threads still exist.
            ``deleted`` — tickets whose threads have been cleaned up.
            ``total_threads`` — estimated Discord thread consumption
                (active + archived, excluding deleted).
            ``limit`` — the thread limit used for percentage calculation.
            ``usage_pct`` — percentage of the limit used.
            ``status`` — human-readable health label.

        AI Notes:
            ``total_threads`` is an estimate from DB records. The real
            Discord thread count may differ if threads were deleted
            outside the bot.
        """
        await self._ensure_ticket_schema_compatibility()
        rows = await BaseRepository.fetch_all(
            """
            SELECT
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN status = 'closed' AND deleted_at IS NULL THEN 1 ELSE 0 END) AS archived,
                SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) AS deleted
            FROM tickets
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        row = rows[0] if rows else None
        active = int((row["active"] if isinstance(row, dict) else row[0]) or 0) if row else 0
        archived = int((row["archived"] if isinstance(row, dict) else row[1]) or 0) if row else 0
        deleted = int((row["deleted"] if isinstance(row, dict) else row[2]) or 0) if row else 0
        total_threads = active + archived
        usage_pct = round((total_threads / thread_limit) * 100, 1) if thread_limit else 0

        if usage_pct >= 95:
            status = "critical"
        elif usage_pct >= 90:
            status = "warning"
        elif usage_pct >= 80:
            status = "notice"
        else:
            status = "healthy"

        return {
            "active": active,
            "archived": archived,
            "deleted": deleted,
            "total_threads": total_threads,
            "limit": thread_limit,
            "usage_pct": usage_pct,
            "status": status,
        }

    async def get_oldest_closed_tickets(
        self,
        guild_id: int,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the oldest closed tickets that still have threads.

        Useful for ``/tickets health`` to show cleanup candidates.

        Args:
            guild_id: Discord guild ID.
            limit: Max number of tickets to return.

        Returns:
            List of ticket dicts ordered oldest-closed first.
        """
        rows = await BaseRepository.fetch_all(
            f"""
            SELECT {_TICKET_COLUMNS}
            FROM tickets
            WHERE guild_id = ? AND status = 'closed' AND deleted_at IS NULL
            ORDER BY closed_at ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return [self._row_to_ticket(r) for r in rows]

    async def get_cleanup_candidates(
        self,
        guild_id: int,
        older_than_days: int,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return closed tickets older than ``older_than_days`` days.

        Only returns tickets whose threads have not been deleted yet
        (``deleted_at IS NULL``) and that are past the safety buffer
        (minimum 30 days).

        Args:
            guild_id: Discord guild ID.
            older_than_days: Minimum days since closure.
            limit: Max number of results; ``None`` for unlimited.

        Returns:
            List of ticket dicts eligible for thread deletion.
        """
        # Safety buffer — never suggest tickets closed less than 30 days ago
        await self._ensure_ticket_schema_compatibility()
        safe_days = max(older_than_days, 30)
        cutoff = int(time.time()) - (safe_days * 86400)
        sql = (
            f"SELECT {_TICKET_COLUMNS} FROM tickets "
            "WHERE guild_id = ? AND status = 'closed' "
            "AND deleted_at IS NULL AND closed_at IS NOT NULL "
            "AND closed_at < ? "
            "ORDER BY closed_at ASC"
        )
        params: list[Any] = [guild_id, cutoff]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await BaseRepository.fetch_all(sql, tuple(params))
        return [self._row_to_ticket(r) for r in rows]

    async def mark_thread_deleted(self, thread_id: int) -> bool:
        """Record that a ticket's Discord thread has been deleted.

        The ticket row is preserved for analytics — only the ``deleted_at``
        timestamp is set.

        Args:
            thread_id: Discord thread ID.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        try:
            await self._ensure_ticket_schema_compatibility()
            now = int(time.time())
            rows = await BaseRepository.execute(
                "UPDATE tickets SET deleted_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
                (now, thread_id),
            )
            if rows > 0:
                self.logger.info("Marked thread %s as deleted", thread_id)
            return rows > 0
        except Exception as e:
            self.logger.exception(
                "Failed to mark thread %s as deleted", thread_id, exc_info=e
            )
            return False

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

        d["prerequisite_role_ids_all"] = TicketService._normalize_role_id_list(
            d.get("prerequisite_role_ids_all")
        )
        d["prerequisite_role_ids_any"] = TicketService._normalize_role_id_list(
            d.get("prerequisite_role_ids_any")
        )
        return d

    @staticmethod
    def _row_to_channel_config(row: Any) -> dict[str, Any]:
        """Convert a database row to a channel config dict."""
        return TicketService._row_to_dict(row, _CHANNEL_CONFIG_COLUMN_NAMES)

    @staticmethod
    def _normalize_role_id_list(raw: Any) -> list[int]:
        """Normalize a list of role IDs into a unique int list."""
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

        normalized: list[int] = []
        for item in parsed:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            if value in normalized:
                continue
            normalized.append(value)

        return normalized

    async def _ensure_category_schema_compatibility(self) -> None:
        """Ensure ticket category columns exist on older DBs.

        AI Notes:
            Checks for role prerequisite columns and ``channel_id`` that may
            be missing on older databases. Uses double-checked locking to
            prevent concurrent ALTER TABLE races.
        """
        if self._category_schema_checked:
            return

        async with self._schema_lock:
            if self._category_schema_checked:
                return

            rows = await BaseRepository.fetch_all("PRAGMA table_info(ticket_categories)")
            column_names = {
                self.extract_column_name(row)
                for row in rows
                if self.extract_column_name(row)
            }

            if "prerequisite_role_ids_all" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_categories "
                        "ADD COLUMN prerequisite_role_ids_all "
                        "TEXT NOT NULL DEFAULT '[]'"
                    )
                    self.logger.info(
                        "Added missing prerequisite_role_ids_all column to "
                        "ticket_categories"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "prerequisite_role_ids_any" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_categories "
                        "ADD COLUMN prerequisite_role_ids_any "
                        "TEXT NOT NULL DEFAULT '[]'"
                    )
                    self.logger.info(
                        "Added missing prerequisite_role_ids_any column to "
                        "ticket_categories"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "channel_id" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_categories "
                        "ADD COLUMN channel_id INTEGER NOT NULL DEFAULT 0"
                    )
                    self.logger.info(
                        "Added missing channel_id column to ticket_categories"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            self._category_schema_checked = True

    async def _ensure_ticket_schema_compatibility(self) -> None:
        """Ensure ``deleted_at`` column exists on older DBs.

        AI Notes:
            Mirrors the ``_ensure_category_schema_compatibility`` pattern.
            Only runs once per process lifetime.  Uses double-checked
            locking via ``_schema_lock``.
        """
        if self._ticket_schema_checked:
            return

        async with self._schema_lock:
            if self._ticket_schema_checked:
                return

            rows = await BaseRepository.fetch_all("PRAGMA table_info(tickets)")
            column_names = {
                self.extract_column_name(row)
                for row in rows
                if self.extract_column_name(row)
            }

            if "deleted_at" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE tickets "
                        "ADD COLUMN deleted_at INTEGER DEFAULT NULL"
                    )
                    self.logger.info("Added missing deleted_at column to tickets")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            self._ticket_schema_checked = True

    async def _ensure_channel_config_schema_compatibility(self) -> None:
        """Ensure public button columns exist on older DBs."""
        if self._channel_config_schema_checked:
            return

        async with self._schema_lock:
            if self._channel_config_schema_checked:
                return

            rows = await BaseRepository.fetch_all(
                "PRAGMA table_info(ticket_channel_configs)"
            )
            column_names = {
                self.extract_column_name(row)
                for row in rows
                if self.extract_column_name(row)
            }

            if "enable_public_button" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_channel_configs "
                        "ADD COLUMN enable_public_button INTEGER NOT NULL DEFAULT 0"
                    )
                    self.logger.info(
                        "Added missing enable_public_button column to ticket_channel_configs"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "public_button_text" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_channel_configs "
                        "ADD COLUMN public_button_text TEXT NOT NULL "
                        "DEFAULT 'Create Public Ticket'"
                    )
                    self.logger.info(
                        "Added missing public_button_text column to ticket_channel_configs"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "public_button_emoji" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_channel_configs "
                        "ADD COLUMN public_button_emoji TEXT DEFAULT '\U0001f310'"
                    )
                    self.logger.info(
                        "Added missing public_button_emoji column to ticket_channel_configs"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "private_button_color" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_channel_configs "
                        "ADD COLUMN private_button_color TEXT DEFAULT NULL"
                    )
                    self.logger.info(
                        "Added missing private_button_color column to ticket_channel_configs"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "public_button_color" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_channel_configs "
                        "ADD COLUMN public_button_color TEXT DEFAULT NULL"
                    )
                    self.logger.info(
                        "Added missing public_button_color column to ticket_channel_configs"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            if "button_order" not in column_names:
                try:
                    await BaseRepository.execute(
                        "ALTER TABLE ticket_channel_configs "
                        "ADD COLUMN button_order TEXT NOT NULL DEFAULT 'private_first'"
                    )
                    self.logger.info(
                        "Added missing button_order column to ticket_channel_configs"
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

            self._channel_config_schema_checked = True

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
