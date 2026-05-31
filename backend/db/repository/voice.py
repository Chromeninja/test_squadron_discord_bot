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

        result = await self.get_voice_channel(guild_id, int(data["voice_channel_id"]))  # type: ignore[arg-type]
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
