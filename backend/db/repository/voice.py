"""VoiceRepository — wrapper around Database for voice channel queries.

The voice_channels table schema:
    id, guild_id, jtc_channel_id, owner_id, voice_channel_id,
    created_at, last_activity, is_active, previous_owner_id

The Database class does not expose dedicated get/list methods for voice
channels (they are accessed via the bot's internal API in production).
This repository issues raw queries via Database.get_connection() to avoid
importing services/ internals into backend/.
"""

from __future__ import annotations

from services.db.database import Database


class VoiceRepository:
    """Repository for voice_channels table and related voice data.

    All methods require guild_id to scope queries to a single guild.
    """

    async def get_jtc_channels(self, guild_id: int) -> list[dict[str, object | None]]:
        """Return all active voice channels for a guild grouped by JTC parent.

        TODO: Database class does not yet expose a list_jtc_channels method.
        This issues a direct query via get_connection().
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, guild_id, jtc_channel_id, owner_id, voice_channel_id,
                       created_at, last_activity, is_active, previous_owner_id
                FROM voice_channels
                WHERE guild_id = ? AND is_active = 1
                ORDER BY jtc_channel_id ASC, created_at ASC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_voice_channel(
        self, guild_id: int, channel_id: int
    ) -> dict[str, object | None] | None:
        """Return a single voice channel row by Discord voice_channel_id, or None."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, guild_id, jtc_channel_id, owner_id, voice_channel_id,
                       created_at, last_activity, is_active, previous_owner_id
                FROM voice_channels
                WHERE guild_id = ? AND voice_channel_id = ?
                """,
                (guild_id, channel_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def create_voice_channel(
        self, guild_id: int, data: dict[str, object | None]
    ) -> dict[str, object | None]:
        """Insert a new voice channel row and return the created row.

        Required keys in data: jtc_channel_id, owner_id, voice_channel_id.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO voice_channels (guild_id, jtc_channel_id, owner_id, voice_channel_id, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    guild_id,
                    data["jtc_channel_id"],
                    data["owner_id"],
                    data["voice_channel_id"],
                ),
            )
            row_id = cursor.lastrowid
            await db.commit()

        if row_id is None:
            raise RuntimeError("Failed to create voice channel row")

        result = await self.get_voice_channel(guild_id, int(data["voice_channel_id"]))  # type: ignore[call-overload]
        if result is None:
            raise RuntimeError("Created voice channel row could not be loaded")
        return result

    async def update_voice_channel(
        self, guild_id: int, channel_id: int, data: dict[str, object | None]
    ) -> dict[str, object | None] | None:
        """Update mutable fields on a voice channel row.

        Supports updating: owner_id, is_active, last_activity, previous_owner_id.
        Returns updated row or None if not found.
        """
        import time

        now = int(time.time())
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE voice_channels
                SET owner_id = COALESCE(?, owner_id),
                    is_active = COALESCE(?, is_active),
                    last_activity = ?,
                    previous_owner_id = COALESCE(?, previous_owner_id)
                WHERE guild_id = ? AND voice_channel_id = ?
                """,
                (
                    data.get("owner_id"),
                    data.get("is_active"),
                    now,
                    data.get("previous_owner_id"),
                    guild_id,
                    channel_id,
                ),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None

        return await self.get_voice_channel(guild_id, channel_id)

    async def delete_voice_channel(self, guild_id: int, channel_id: int) -> bool:
        """Mark a voice channel as inactive (soft-delete via is_active=0).

        Returns True if a row was updated.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE voice_channels
                SET is_active = 0
                WHERE guild_id = ? AND voice_channel_id = ?
                """,
                (guild_id, channel_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    # ── Cooldown management ──────────────────────────────────────────────────

    async def check_cooldown(
        self,
        guild_id: int,
        jtc_channel_id: int,
        user_id: int,
        cooldown_seconds: int,
    ) -> bool:
        """Return True if the user is still within the cooldown window."""
        import time

        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT timestamp FROM voice_cooldowns
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                (guild_id, jtc_channel_id, user_id),
            )
            row = await cursor.fetchone()

        if row is None:
            return False
        return (int(time.time()) - row[0]) < cooldown_seconds

    async def update_cooldown(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> None:
        """Upsert the cooldown timestamp for a user to now."""
        import time

        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO voice_cooldowns
                (guild_id, jtc_channel_id, user_id, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (guild_id, jtc_channel_id, user_id, int(time.time())),
            )
            await db.commit()

    # ── Channel ownership queries ────────────────────────────────────────────

    async def get_user_channel_in_jtc(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> int | None:
        """Return the active voice_channel_id owned by user_id under a specific JTC."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT voice_channel_id FROM voice_channels
                WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (guild_id, jtc_channel_id, user_id),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else None

    async def get_any_user_channel(self, guild_id: int, user_id: int) -> int | None:
        """Return any active voice_channel_id owned by user_id in the guild."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT voice_channel_id FROM voice_channels
                WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else None

    async def get_jtc_for_owned_channel(
        self, guild_id: int, voice_channel_id: int, owner_id: int
    ) -> int | None:
        """Return the JTC channel ID for an active channel owned by owner_id."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT jtc_channel_id FROM voice_channels
                WHERE guild_id = ? AND voice_channel_id = ? AND owner_id = ? AND is_active = 1
                """,
                (guild_id, voice_channel_id, owner_id),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else None

    async def get_user_channel_info(
        self, guild_id: int, user_id: int
    ) -> dict[str, object | None] | None:
        """Return a dict of the user's active channel row, or None."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT guild_id, jtc_channel_id, voice_channel_id, owner_id,
                       created_at, last_activity, is_active
                FROM voice_channels
                WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                LIMIT 1
                """,
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "guild_id": row[0],
            "jtc_channel_id": row[1],
            "voice_channel_id": row[2],
            "owner_id": row[3],
            "created_at": row[4],
            "last_activity": row[5],
            "is_active": bool(row[6]),
        }

    async def get_all_active_channels(
        self, guild_id: int
    ) -> list[dict[str, object | None]]:
        """Return all active voice channel rows for a guild (owner, channel, created_at)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT owner_id, voice_channel_id, created_at
                FROM voice_channels
                WHERE guild_id = ? AND is_active = 1
                ORDER BY created_at DESC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
        return [
            {"owner_id": r[0], "voice_channel_id": r[1], "created_at": r[2]}
            for r in rows
        ]

    async def get_active_channel_ids(self, guild_id: int) -> list[int]:
        """Return a flat list of active voice_channel_id values for a guild."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT voice_channel_id FROM voice_channels WHERE guild_id = ? AND is_active = 1",
                (guild_id,),
            )
            rows = await cursor.fetchall()
        return [int(r[0]) for r in rows]

    # ── Cleanup / purge ──────────────────────────────────────────────────────

    async def cleanup_channel_records(
        self, guild_id: int, voice_channel_id: int
    ) -> None:
        """Hard-delete all DB records for a voice channel (settings + channel row)."""
        async with Database.get_connection() as db:
            await db.execute("BEGIN")
            await db.execute(
                "DELETE FROM voice_channel_settings WHERE guild_id = ? AND voice_channel_id = ?",
                (guild_id, voice_channel_id),
            )
            await db.execute(
                "DELETE FROM voice_channels WHERE guild_id = ? AND voice_channel_id = ?",
                (guild_id, voice_channel_id),
            )
            await db.commit()

    async def purge_voice_data(
        self, guild_id: int, user_id: int | None = None
    ) -> dict[str, int]:
        """Delete all voice-related rows for a guild (or a single user within it).

        Returns a dict mapping table name → rows deleted.
        """
        voice_tables: dict[str, str] = {
            "voice_channels": "owner_id",
            "voice_channel_settings": "owner_id",
            "voice_cooldowns": "user_id",
            "channel_settings": "user_id",
            "channel_permissions": "user_id",
            "channel_ptt_settings": "user_id",
            "channel_priority_speaker_settings": "user_id",
            "channel_soundboard_settings": "user_id",
        }
        deleted: dict[str, int] = {}
        async with Database.get_connection() as db:
            await db.execute("BEGIN")
            for table, user_col in voice_tables.items():
                if user_id is not None:
                    cursor = await db.execute(
                        f"DELETE FROM {table} WHERE guild_id = ? AND {user_col} = ?",
                        (guild_id, user_id),
                    )
                else:
                    cursor = await db.execute(
                        f"DELETE FROM {table} WHERE guild_id = ?",
                        (guild_id,),
                    )
                deleted[table] = cursor.rowcount
            await db.commit()
        return deleted

    async def purge_stale_jtc_data(
        self, guild_id: int, stale_jtc_ids: set[int]
    ) -> dict[str, int]:
        """Delete all voice rows scoped to the given (now-stale) JTC channel IDs.

        Returns a dict mapping table name → rows deleted.
        """
        if not stale_jtc_ids:
            return {}

        jtc_tables = {
            "voice_channels",
            "voice_channel_settings",
            "voice_cooldowns",
            "channel_settings",
            "channel_permissions",
            "channel_ptt_settings",
            "channel_priority_speaker_settings",
            "channel_soundboard_settings",
        }
        jtc_list = list(stale_jtc_ids)
        placeholders = ",".join("?" * len(jtc_list))
        deleted: dict[str, int] = {}
        async with Database.get_connection() as db:
            await db.execute("BEGIN")
            for table in jtc_tables:
                cursor = await db.execute(
                    f"DELETE FROM {table} WHERE guild_id = ? AND jtc_channel_id IN ({placeholders})",
                    [guild_id, *jtc_list],
                )
                deleted[table] = cursor.rowcount
            await db.commit()
        return deleted
