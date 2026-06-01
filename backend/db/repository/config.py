"""ConfigRepository — wrapper around Database for guild settings (config) queries.

The guild_settings table schema:
    guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,
    PRIMARY KEY (guild_id, key)

The guild_settings_audit table schema:
    id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
    key TEXT NOT NULL, old_value TEXT, new_value TEXT,
    changed_by_user_id INTEGER, changed_at INTEGER

Values in guild_settings are stored as TEXT. Non-string values are JSON-encoded
on write and JSON-decoded on read. If JSON decoding fails, the raw string value
is returned. An audit row is written on every setting change.

The Database class does not expose dedicated config methods, so this repository
issues raw queries via Database.get_connection().
"""

from __future__ import annotations

import json

from services.db.database import Database


class ConfigRepository:
    """Repository for guild_settings table and related config data.

    All methods require guild_id to scope queries to a single guild.
    Values are stored as TEXT in the database and automatically JSON-encoded/decoded.
    """

    @staticmethod
    def _decode_value(text: str | None) -> object | None:
        """Decode a TEXT value from the database.

        If the value is NULL, return None.
        If it is a JSON string, parse and return the decoded value.
        If JSON parsing fails, return the raw string.
        """
        if text is None:
            return None
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return text

    @staticmethod
    def _encode_value(value: object | None) -> str | None:
        """Encode a value for storage in the database.

        If None, return None (stored as NULL).
        Otherwise JSON-encode the value.
        """
        if value is None:
            return None
        return json.dumps(value)

    async def get_config(self, guild_id: int) -> dict[str, object | None]:
        """Return all settings for a guild as a dict {key: decoded_value}.

        SELECT key, value WHERE guild_id=? → return {key: decoded_value}
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT key, value
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()
        return {row["key"]: self._decode_value(row["value"]) for row in rows}

    async def get_setting(self, guild_id: int, key: str) -> object | None:
        """Return a single setting value, or None if the setting does not exist.

        SELECT value WHERE guild_id=? AND key=? → decoded value, or None if no row
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT value
                FROM guild_settings
                WHERE guild_id = ? AND key = ?
                """,
                (guild_id, key),
            )
            row = await cursor.fetchone()

        # Distinguish "no row" from "value is null"
        if row is None:
            return None
        return self._decode_value(row["value"])

    async def set_setting(
        self,
        guild_id: int,
        key: str,
        value: object | None = None,
        changed_by_user_id: int | None = None,
    ) -> None:
        """Set a setting and write an audit row.

        Reads the old value, UPSERT (INSERT ... ON CONFLICT UPDATE),
        then INSERT audit row with old/new JSON values.
        """
        # Read old value
        old_value = await self.get_setting(guild_id, key)
        old_value_text = self._encode_value(old_value)

        # UPSERT
        encoded_value = self._encode_value(value)
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
                """,
                (guild_id, key, encoded_value),
            )

            # Write audit row
            new_value_text = self._encode_value(value)
            await db.execute(
                """
                INSERT INTO guild_settings_audit
                (guild_id, key, old_value, new_value, changed_by_user_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, key, old_value_text, new_value_text, changed_by_user_id),
            )

            await db.commit()

    async def update_config(
        self,
        guild_id: int,
        data: dict[str, object | None],
        changed_by_user_id: int | None = None,
    ) -> dict[str, object | None]:
        """Update multiple settings and return the updated full config.

        Call set_setting for each key in data, then return get_config(guild_id).
        """
        for key, value in data.items():
            await self.set_setting(guild_id, key, value, changed_by_user_id)
        return await self.get_config(guild_id)
