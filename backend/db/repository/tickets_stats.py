"""_TicketStatsMixin — ticket statistics and diagnostics queries mixin."""

from __future__ import annotations

import time

from services.db.database import Database


class _TicketStatsMixin:
    """Ticket statistics and diagnostics queries (mixin)."""

    async def get_open_tickets(
        self,
        guild_id: int,
        user_id: int | None = None,
    ) -> list[dict[str, object | None]]:
        """Return open tickets, optionally filtered by user."""
        where = "WHERE guild_id = ? AND status = 'open' AND deleted_at IS NULL"
        params: list[object] = [guild_id]
        if user_id is not None:
            where += " AND user_id = ?"
            params.append(user_id)

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM tickets " + where + " ORDER BY created_at DESC",
                tuple(params),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_ticket_count(
        self,
        guild_id: int,
        status: str | None = None,
    ) -> int:
        """Return total ticket count, optionally filtered by status."""
        where = "WHERE guild_id = ? AND deleted_at IS NULL"
        params: list[object] = [guild_id]
        if status:
            where += " AND status = ?"
            params.append(status)

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM tickets " + where,
                tuple(params),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    async def get_ticket_stats(self, guild_id: int) -> dict[str, int]:
        """Return ticket statistics for a guild.

        Returns:
            Dict with keys: open, closed, total.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status, COUNT(*) AS cnt FROM tickets "
                "WHERE guild_id = ? AND deleted_at IS NULL GROUP BY status",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            counts: dict[str, int] = {"open": 0, "closed": 0}
            for row in rows:
                row_dict = dict(row)
                status = row_dict["status"]
                cnt = row_dict["cnt"]
                if status in counts:
                    counts[status] = int(cnt)
            return {
                "open": counts["open"],
                "closed": counts["closed"],
                "total": counts["open"] + counts["closed"],
            }

    async def get_open_ticket_count(
        self,
        guild_id: int,
        user_id: int,
    ) -> int:
        """Return the number of currently open tickets for a user in a guild."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND user_id = ? AND status = 'open'
                    AND deleted_at IS NULL
                """,
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    async def get_thread_health(
        self, guild_id: int, thread_limit: int = 1000
    ) -> dict[str, object | None]:
        """Return thread usage data for a guild (active/archived/deleted counts + usage status)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
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
            row = await cursor.fetchone()
        d = dict(row) if row else {}
        active = int(d.get("active") or 0)
        archived = int(d.get("archived") or 0)
        deleted = int(d.get("deleted") or 0)
        total_threads = active + archived
        usage_pct = (
            round((total_threads / thread_limit) * 100, 1) if thread_limit else 0.0
        )
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
        self, guild_id: int, limit: int = 5
    ) -> list[dict[str, object | None]]:
        """Return the oldest closed tickets that still have threads (deleted_at IS NULL)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM tickets
                WHERE guild_id = ? AND status = 'closed' AND deleted_at IS NULL
                ORDER BY closed_at ASC LIMIT ?
                """,
                (guild_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_cleanup_candidates(
        self, guild_id: int, older_than_days: int, limit: int | None = None
    ) -> list[dict[str, object | None]]:
        """Return closed tickets older than older_than_days (min 30-day safety buffer)."""
        safe_days = max(older_than_days, 30)
        cutoff = int(time.time()) - (safe_days * 86400)
        sql = (
            "SELECT * FROM tickets WHERE guild_id = ? AND status = 'closed' "
            "AND deleted_at IS NULL AND closed_at IS NOT NULL AND closed_at < ? "
            "ORDER BY closed_at ASC"
        )
        params: list[object] = [guild_id, cutoff]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        async with Database.get_connection() as db:
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def can_reopen(
        self,
        thread_id: int,
        reopen_window_hours: int = 48,
    ) -> bool:
        """Check whether a closed ticket is still within the reopen window.

        Returns:
            True if the ticket exists, is closed, and within the window.
        """
        cutoff = int(time.time()) - (reopen_window_hours * 3600)
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM tickets
                WHERE thread_id = ? AND status = 'closed' AND closed_at > ?
                """,
                (thread_id, cutoff),
            )
            row = await cursor.fetchone()
            return row is not None

    async def mark_thread_deleted(self, thread_id: int) -> bool:
        """Record that a ticket's Discord thread has been deleted.

        Returns:
            True if a row was updated, False otherwise.
        """
        try:
            now = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "UPDATE tickets SET deleted_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
                    (now, thread_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def get_cooldown_reset(
        self,
        guild_id: int,
        user_id: int,
        global_reset_id: int = 0,
    ) -> int | None:
        """Return the most recent cooldown reset timestamp for the user.

        Checks both per-user resets and the global reset (user_id=0).
        Returns None if no reset record exists.
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT MAX(reset_at) FROM ticket_cooldown_resets
                    WHERE guild_id = ? AND user_id IN (?, ?)
                    """,
                    (guild_id, global_reset_id, user_id),
                )
                row = await cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

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

        Returns:
            The new channel config row ID, or None on failure.
        """
        try:
            cols = ["guild_id", "channel_id"]
            vals: list[object] = [guild_id, channel_id]

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

            async with Database.get_connection() as db:
                cursor = await db.execute(
                    f"""
                    INSERT INTO ticket_channel_configs ({col_names})
                    VALUES ({placeholders})
                    """,
                    tuple(vals),
                )
                config_id = cursor.lastrowid
                await db.commit()
                return int(config_id) if config_id else None
        except Exception:
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

        Returns:
            True if the config was updated, False otherwise.
        """
        try:
            if new_channel_id is not None and new_channel_id != channel_id:
                # Check if new_channel_id already exists
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        """
                        SELECT 1
                        FROM ticket_channel_configs
                        WHERE guild_id = ? AND channel_id = ?
                        """,
                        (guild_id, new_channel_id),
                    )
                    existing = await cursor.fetchone()
                if existing:
                    return False

            updates: list[str] = []
            vals: list[object] = []

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
                return False

            vals.append(guild_id)
            vals.append(channel_id)

            async with Database.get_connection() as db:
                cursor = await db.execute(
                    f"""
                    UPDATE ticket_channel_configs
                    SET {", ".join(updates)}
                    WHERE guild_id = ? AND channel_id = ?
                    """,
                    tuple(vals),
                )
                await db.commit()

                if cursor.rowcount > 0:
                    if new_channel_id is not None and new_channel_id != channel_id:
                        await db.execute(
                            """
                            UPDATE ticket_categories
                            SET channel_id = ?
                            WHERE guild_id = ? AND channel_id = ?
                            """,
                            (new_channel_id, guild_id, channel_id),
                        )
                        await db.commit()

                return cursor.rowcount > 0
        except Exception:
            return False
