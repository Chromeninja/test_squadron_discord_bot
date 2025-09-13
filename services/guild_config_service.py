"""
Guild Configuration Service

Provides a centralized service for managing guild-scoped settings with caching,
specialized helpers for voice configuration, and migration from legacy settings.
"""

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

from utils.logging import get_logger

from services.db.database import Database

logger = get_logger(__name__)

T = TypeVar('T')
JSONable = str | int | float | bool | None | dict[str, Any] | list[Any]


class GuildConfigService:
    """
    Service for managing guild-scoped configuration settings.

    Features:
    - In-memory caching with configurable TTL
    - Race-safe writes using per-key locks
    - High-level helpers for voice settings (JTC channels, voice categories)
    - Generic get/set methods with JSON encoding/decoding
    - Non-destructive legacy settings migration
    """

    def __init__(self, *, ttl_seconds: int = 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[tuple[int, str], tuple[Any, float]] = {}  # (guild_id, key) -> (value, timestamp)
        self._cache_lock = asyncio.Lock()
        self._write_locks: dict[tuple[int, str], asyncio.Lock] = {}
        self._write_locks_lock = asyncio.Lock()

    async def get(
        self,
        guild_id: int,
        key: str,
        *,
        parser: Callable[[str], T] | None = None
    ) -> T | None:
        """
        Get a guild setting with optional parsing.

        Args:
            guild_id: Discord guild ID
            key: Setting key
            parser: Optional function to parse the stored string value

        Returns:
            Parsed value or None if not found
        """
        cache_key = (guild_id, key)
        now = time.monotonic()

        # Check cache first
        async with self._cache_lock:
            if cache_key in self._cache:
                value, timestamp = self._cache[cache_key]
                if now - timestamp < self.ttl_seconds:
                    logger.debug(f"Cache hit for guild {guild_id}, key {key}")
                    return value  # type: ignore[no-any-return]
                else:
                    # Expired, remove from cache
                    del self._cache[cache_key]
                    logger.debug(f"Cache expired for guild {guild_id}, key {key}")

        # Load from database
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
                (guild_id, key)
            )
            row = await cursor.fetchone()

        if row is None:
            logger.debug(f"No setting found for guild {guild_id}, key {key}")
            return None

        value_str = row[0]
        if value_str is None:
            return None

        # Parse the value
        try:
            if parser:
                parsed_value = parser(value_str)
            else:
                # Default: try JSON decode, fall back to string
                try:
                    parsed_value = json.loads(value_str)
                except (json.JSONDecodeError, TypeError):
                    parsed_value = value_str
        except Exception as e:
            logger.warning(f"Failed to parse setting {key} for guild {guild_id}: {e}")
            return None

        # Update cache
        async with self._cache_lock:
            self._cache[cache_key] = (parsed_value, now)

        logger.debug(f"Loaded setting for guild {guild_id}, key {key}")
        return parsed_value

    async def set(self, guild_id: int, key: str, value: JSONable) -> None:
        """
        Set a guild setting with cache invalidation.

        Args:
            guild_id: Discord guild ID
            key: Setting key
            value: Setting value (must be JSON serializable)
        """
        cache_key = (guild_id, key)

        # Get or create write lock for this key
        async with self._write_locks_lock:
            if cache_key not in self._write_locks:
                self._write_locks[cache_key] = asyncio.Lock()
            write_lock = self._write_locks[cache_key]

        # Serialize writes for the same key to avoid race conditions
        async with write_lock:
            # Store in database
            value_str = json.dumps(value) if value is not None else None
            async with Database.get_connection() as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                    VALUES (?, ?, ?)
                    """,
                    (guild_id, key, value_str)
                )
                await db.commit()

            # Update cache
            now = time.monotonic()
            async with self._cache_lock:
                self._cache[cache_key] = (value, now)

        logger.debug(f"Set guild {guild_id} setting {key} = {value}")

    async def set_guild_setting(self, guild_id: int, key: str, value: JSONable) -> None:
        """
        Alias for set() method for backward compatibility.

        Args:
            guild_id: Discord guild ID
            key: Setting key
            value: Setting value (must be JSON serializable)
        """
        await self.set(guild_id, key, value)

    async def get_join_to_create_channels(self, guild_id: int) -> list[int]:
        """
        Get the list of Join-to-Create channel IDs for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of channel IDs, empty list if not configured
        """
        channels = await self.get(guild_id, "join_to_create_channel_ids")
        if isinstance(channels, list):
            return [int(cid) for cid in channels if isinstance(cid, int | str)]
        return []

    async def set_join_to_create_channels(self, guild_id: int, channel_ids: list[int]) -> None:
        """
        Set the Join-to-Create channel IDs for a guild.

        Args:
            guild_id: Discord guild ID
            channel_ids: List of Discord channel IDs
        """
        await self.set(guild_id, "join_to_create_channel_ids", channel_ids)

    async def get_voice_category_id(self, guild_id: int) -> int | None:
        """
        Get the voice category ID for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Voice category ID or None if not configured
        """
        category_id = await self.get(guild_id, "voice_category_id")
        if isinstance(category_id, int | str):
            return int(category_id)
        return None

    async def set_voice_category_id(self, guild_id: int, category_id: int | None) -> None:
        """
        Set the voice category ID for a guild.

        Args:
            guild_id: Discord guild ID
            category_id: Discord category ID or None to unset
        """
        await self.set(guild_id, "voice_category_id", category_id)

    async def maybe_migrate_legacy_settings(self, bot: Any) -> None:
        """
        Migrate legacy voice settings to guild-specific settings if needed.

        Migration logic:
        - If guild_settings already has JTC entries, do nothing
        - If exactly one guild exists and legacy settings exist, migrate them
        - If zero or multiple guilds exist, log a warning and do nothing

        Args:
            bot: Discord bot instance (for accessing guilds)
        """
        try:
            # Check if we already have guild-specific settings
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM guild_settings WHERE key = ?",
                    ("join_to_create_channel_ids",)
                )
                existing_count = (await cursor.fetchone())[0]

                if existing_count > 0:
                    logger.debug("Guild-specific JTC settings already exist, skipping migration")
                    return

                # Check for legacy settings
                cursor = await db.execute(
                    "SELECT key, value FROM settings WHERE key IN (?, ?)",
                    ("join_to_create_channel_ids", "voice_category_id")
                )
                legacy_settings = {row[0]: row[1] for row in await cursor.fetchall()}

                if not legacy_settings:
                    logger.debug("No legacy voice settings found, skipping migration")
                    return

            # Check guild count for migration safety
            guild_count = len(bot.guilds)
            if guild_count == 0:
                logger.warning(
                    "Cannot migrate legacy voice settings: bot is not in any guilds. "
                    "Please manually configure guild-specific settings after the bot joins a guild."
                )
                return
            elif guild_count > 1:
                logger.warning(
                    f"Cannot auto-migrate legacy voice settings: bot is in {guild_count} guilds. "
                    "Please manually configure guild-specific settings for each guild using the "
                    "/voice admin commands."
                )
                return

            # Safe to migrate: exactly one guild
            guild = bot.guilds[0]
            guild_id = guild.id

            migrated_settings = []

            # Migrate JTC channels
            if "join_to_create_channel_ids" in legacy_settings:
                try:
                    legacy_jtc = json.loads(legacy_settings["join_to_create_channel_ids"])
                    await self.set_join_to_create_channels(guild_id, legacy_jtc)
                    migrated_settings.append("join_to_create_channel_ids")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to migrate legacy JTC channels: {e}")

            # Migrate voice category
            if "voice_category_id" in legacy_settings:
                try:
                    legacy_category = int(legacy_settings["voice_category_id"])
                    await self.set_voice_category_id(guild_id, legacy_category)
                    migrated_settings.append("voice_category_id")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to migrate legacy voice category: {e}")

            if migrated_settings:
                logger.info(
                    f"Successfully migrated legacy voice settings to guild {guild.name} ({guild_id}): "
                    f"{', '.join(migrated_settings)}"
                )

        except Exception as e:
            logger.exception(f"Error during legacy settings migration: {e}")

    async def _load_many(self, keys: list[tuple[int, str]]) -> dict[tuple[int, str], Any]:
        """
        Batch load multiple settings from the database.

        Args:
            keys: List of (guild_id, key) tuples

        Returns:
            Dict mapping cache keys to values
        """
        if not keys:
            return {}

        # Build parameterized query for batch loading
        placeholders = ",".join(["(?,?)"] * len(keys))
        params = []
        for guild_id, key in keys:
            params.extend([guild_id, key])

        results = {}
        async with Database.get_connection() as db:
            cursor = await db.execute(
                f"""
                SELECT guild_id, key, value
                FROM guild_settings
                WHERE (guild_id, key) IN ({placeholders})
                """,
                params
            )

            now = time.monotonic()
            async for row in cursor:
                guild_id, key, value_str = row
                cache_key = (guild_id, key)

                if value_str is None:
                    parsed_value = None
                else:
                    try:
                        parsed_value = json.loads(value_str)
                    except (json.JSONDecodeError, TypeError):
                        parsed_value = value_str

                results[cache_key] = parsed_value

                # Cache the result
                async with self._cache_lock:
                    self._cache[cache_key] = (parsed_value, now)

        return results

    async def clear_cache(self, guild_id: int | None = None, key: str | None = None) -> None:
        """
        Clear cached settings.

        Args:
            guild_id: If provided, clear cache only for this guild
            key: If provided (with guild_id), clear cache only for this specific key
        """
        async with self._cache_lock:
            if guild_id is None:
                # Clear entire cache
                self._cache.clear()
                logger.debug("Cleared entire guild config cache")
            elif key is None:
                # Clear cache for specific guild
                keys_to_remove = [k for k in self._cache if k[0] == guild_id]
                for k in keys_to_remove:
                    del self._cache[k]
                logger.debug(f"Cleared cache for guild {guild_id}")
            else:
                # Clear cache for specific guild and key
                cache_key = (guild_id, key)
                self._cache.pop(cache_key, None)
                logger.debug(f"Cleared cache for guild {guild_id}, key {key}")
