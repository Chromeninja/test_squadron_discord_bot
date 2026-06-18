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

    async def get_guild_roles(self, guild_id: int) -> dict[str, object | None]:
        """Return role configuration for a guild, mirroring ConfigService.get_guild_roles.

        Returns a dict with role names as keys and role IDs (int or list[int]) as values,
        extracted from guild_settings using the same key names and parsing logic as ConfigService.
        """
        roles: dict[str, object | None] = {}

        # Single role IDs (stored as list but we extract first element)
        single_role_keys = [
            ("roles.bot_verified_role", "bot_verified_role_id"),
            ("roles.main_role", "main_role_id"),
            ("roles.affiliate_role", "affiliate_role_id"),
            ("roles.non_member_role", "non_member_role_id"),
        ]

        for setting_key, output_key in single_role_keys:
            role_ids = await self.get_setting(guild_id, setting_key)
            if role_ids:
                # Handle both list and single values
                if isinstance(role_ids, list) and role_ids:
                    roles[output_key] = role_ids[0]
                elif not isinstance(role_ids, list):
                    roles[output_key] = role_ids

        # List-based role IDs (already parsed as list[int])
        admin_roles = await self.get_setting(guild_id, "roles.bot_admins")
        if admin_roles and isinstance(admin_roles, list):
            roles["bot_admin_role_ids"] = admin_roles

        event_coordinator_roles = await self.get_setting(
            guild_id, "roles.event_coordinators"
        )
        if event_coordinator_roles and isinstance(event_coordinator_roles, list):
            roles["event_coordinator_role_ids"] = event_coordinator_roles

        selectable_roles = await self.get_setting(guild_id, "selectable_roles")
        if selectable_roles and isinstance(selectable_roles, list):
            roles["selectable_roles"] = selectable_roles

        return roles

    async def get_guild_channels(self, guild_id: int) -> dict[str, object | None]:
        """Return channel configuration for a guild, mirroring ConfigService.get_guild_channels.

        Returns a dict with channel names as keys and channel IDs (int) as values,
        extracted from guild_settings using the same key names and parsing logic as ConfigService.
        """
        channels: dict[str, object | None] = {}

        channel_keys = [
            "verification_channel_id",
            "bot_spam_channel_id",
            "public_announcement_channel_id",
            "leadership_announcement_channel_id",
        ]

        for channel_key in channel_keys:
            channel_id = await self.get_setting(guild_id, f"channels.{channel_key}")
            if isinstance(channel_id, (int, str)):
                try:
                    channels[channel_key] = int(channel_id)
                except (TypeError, ValueError):
                    pass

        return channels

    async def get_jtc_channels(self, guild_id: int) -> list[int]:
        """Return join-to-create voice channels for a guild as list[int].

        Mirrors ConfigService.get_guild_jtc_channels.
        """
        channels = await self.get_setting(guild_id, "voice.jtc_channels")
        if not channels:
            return []
        if not isinstance(channels, list):
            return []
        try:
            return [int(c) for c in channels]
        except (TypeError, ValueError):
            return []

    async def get_role_ids(self, guild_id: int, role_key: str) -> list[int]:
        """Get a list of role IDs for a given setting key.

        Generic method used by get_bot_admin_role_ids, get_discord_manager_role_ids, etc.
        Replicates the storage format: stored as list[int] in JSON, parsed to list[int].
        """
        value = await self.get_setting(guild_id, role_key)
        if not value:
            return []
        if not isinstance(value, list):
            return []
        try:
            return [int(v) for v in value if v is not None]
        except (TypeError, ValueError):
            return []

    async def get_single_setting_int(self, guild_id: int, key: str) -> int | None:
        """Get a single setting and parse it as an int.

        Used by get_verified_role_id, channel IDs, etc.
        Replicates ConfigService._safe_int parsing logic.
        """
        value = await self.get_setting(guild_id, key)
        if not isinstance(value, (int, str)):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
