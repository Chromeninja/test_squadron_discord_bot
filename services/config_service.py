"""Configuration service for per-guild settings and global configuration."""

import asyncio
import copy
import json
from collections.abc import Callable
from typing import Any

from config.config_loader import ConfigLoader
from services.db.repository import BaseRepository

from .base import BaseService

SETTINGS_VERSION_KEY = "meta.settings_version"


# -----------------------------------------------------------------------------
# Common Configuration Keys (centralized constants)
# -----------------------------------------------------------------------------

# Organization settings
CONFIG_ORG_SID = "organization.sid"
CONFIG_ORG_NAME = "organization.name"

# Role settings
CONFIG_VERIFIED_ROLE = "roles.bot_verified_role"
CONFIG_MAIN_ROLE = "roles.main_role"
CONFIG_AFFILIATE_ROLE = "roles.affiliate_role"
CONFIG_NONMEMBER_ROLE = "roles.non_member_role"
CONFIG_BOT_ADMINS = "roles.bot_admins"
CONFIG_DISCORD_MANAGERS = "roles.discord_managers"
CONFIG_MODERATORS = "roles.moderators"
CONFIG_STAFF = "roles.staff"

# Channel settings
CONFIG_VERIFICATION_CHANNEL = "channels.verification_channel_id"
CONFIG_BOT_SPAM_CHANNEL = "channels.bot_spam_channel_id"
CONFIG_PUBLIC_ANNOUNCE_CHANNEL = "channels.public_announcement_channel_id"
CONFIG_LEADERSHIP_ANNOUNCE_CHANNEL = "channels.leadership_announcement_channel_id"

# Voice settings
CONFIG_JTC_CHANNELS = "voice.jtc_channels"


class ConfigService(BaseService):
    """
    Service for managing per-guild configuration and global settings.

    Provides a clean interface for accessing guild-specific settings while
    falling back to global defaults.
    """

    def __init__(self, config_loader: ConfigLoader | None = None) -> None:
        super().__init__("config")
        self._global_config: dict[str, Any] = {}
        self._guild_cache: dict[int, dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._guild_versions: dict[int, str | None] = {}
        # Use centralized ConfigLoader to avoid duplicate path resolution/reads
        self._config_loader = config_loader or ConfigLoader()

    async def _initialize_impl(self) -> None:
        """Load global configuration."""
        await self._load_global_config()

    async def _load_global_config(self) -> None:
        """Load global configuration from the centralized ConfigLoader."""
        config = self._config_loader.load_config()
        # Work on a copy so service-specific coercions do not mutate the shared loader cache
        self._global_config = copy.deepcopy(config) if isinstance(config, dict) else {}

        # Normalize role IDs to integers at load time
        self._coerce_role_types(self._global_config)

        if self._global_config:
            self.logger.info("Global configuration loaded successfully")
        else:
            self.logger.warning("Global config empty or missing; using defaults")

    def _coerce_role_types(self, config: dict[str, Any]) -> None:
        """
        Coerce role IDs to integers at config boundary.

        This ensures all role IDs are consistently typed throughout the codebase,
        eliminating the need for scattered int() calls.

        Args:
            config: Configuration dictionary to normalize (modified in place)
        """
        if not isinstance(config, dict):
            return

        # Normalize roles section
        if "roles" in config and isinstance(config["roles"], dict):
            roles = config["roles"]

            # Convert list-based role configs
            for key in ["bot_admins"]:
                if key in roles and isinstance(roles[key], list):
                    roles[key] = [int(role_id) for role_id in roles[key] if role_id]

            # Convert single role ID configs
            for key in [
                "bot_verified_role_id",
                "main_role_id",
                "affiliate_role_id",
                "non_member_role_id",
            ]:
                if key in roles and roles[key] is not None:
                    try:
                        roles[key] = int(roles[key])
                    except (ValueError, TypeError):
                        self.logger.warning(f"Invalid role ID for {key}: {roles[key]}")
                        roles[key] = None

    async def get(
        self,
        guild_id: int,
        key: str,
        default: Any = None,
        parser: Callable[[Any], Any] | None = None,
    ) -> Any:
        """
        Get a setting for a specific guild with optional parsing.

        Args:
            guild_id: Discord guild ID
            key: Setting key (supports dot notation like "roles.admin")
            default: Default value if setting not found
            parser: Optional function to parse/convert the value (e.g., int, float)

        Returns:
            Setting value (parsed if parser provided) or default
        """
        self.logger.debug(
            f"ConfigService.get: guild_id={guild_id}, key='{key}', parser={parser.__name__ if parser else None}"
        )
        value = await self.get_guild_setting(guild_id, key, default)
        self.logger.debug(
            f"  ConfigService.get result: {value} (type: {type(value).__name__ if value is not None else 'None'})"
        )

        # Apply parser if provided and value is not None/default
        if parser and value is not None and value != default:
            try:
                return parser(value)
            except (ValueError, TypeError) as e:
                self.logger.warning(
                    f"Failed to parse config value '{value}' for key '{key}' "
                    f"with parser {parser.__name__}: {e}"
                )
                return default

        return value

    async def get_guild_setting(
        self, guild_id: int, key: str, default: Any = None
    ) -> Any:
        """
        Get a setting for a specific guild.

        Args:
            guild_id: Discord guild ID
            key: Setting key (supports dot notation like "roles.admin")
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        self._ensure_initialized()

        # Check guild-specific settings first
        guild_settings = await self._get_guild_settings(guild_id)

        # First try exact key match (for flat keys like "test.setting")
        if key in guild_settings:
            return guild_settings[key]

        # Then try nested key support for dot notation
        value = self._get_nested_value(guild_settings, key)
        if value is not None:
            return value

        # Fall back to global config
        global_value = self._get_nested_value(self._global_config, key)
        return global_value if global_value is not None else default

    async def set_guild_setting(self, guild_id: int, key: str, value: Any) -> None:
        """
        Set a guild-specific setting.

        Args:
            guild_id: Discord guild ID
            key: Setting key
            value: Setting value (will be JSON serialized)
        """
        self._ensure_initialized()

        import json

        # Store in database
        await BaseRepository.execute(
            """
            INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
            VALUES (?, ?, ?)
            """,
            (guild_id, key, json.dumps(value)),
        )

        # Update cache
        async with self._cache_lock:
            if guild_id not in self._guild_cache:
                self._guild_cache[guild_id] = {}
            self._guild_cache[guild_id][key] = value
            if key == SETTINGS_VERSION_KEY:
                self._guild_versions[guild_id] = self._extract_version_value(value)

        self.logger.debug(f"Set guild {guild_id} setting {key} = {value}")

    async def get_global_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a global setting.

        Args:
            key: Setting key (supports dot notation)
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        self._ensure_initialized()
        value = self._get_nested_value(self._global_config, key)
        return value if value is not None else default

    async def _get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        """Get all settings for a guild, using cache when possible."""
        async with self._cache_lock:
            if guild_id in self._guild_cache:
                self.logger.debug(
                    f"Cache HIT for guild {guild_id}: {len(self._guild_cache[guild_id])} settings"
                )
                return self._guild_cache[guild_id]

        self.logger.debug(f"Cache MISS for guild {guild_id} - loading from database")

        # Load from database
        import json

        settings = {}
        rows = await BaseRepository.fetch_all(
            "SELECT key, value FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        for row in rows:
            key, value_json = row
            try:
                settings[key] = json.loads(value_json)
                self.logger.debug(f"  Loaded setting: {key} = {settings[key]}")
            except (json.JSONDecodeError, TypeError):
                self.logger.warning(
                    f"Failed to parse setting {key} for guild {guild_id}"
                )

        # Cache the settings
        async with self._cache_lock:
            self._guild_cache[guild_id] = settings
            self._guild_versions[guild_id] = self._extract_version_value(
                settings.get(SETTINGS_VERSION_KEY)
            )

        self.logger.info(
            f"Loaded {len(settings)} settings from database for guild {guild_id}"
        )
        if settings:
            self.logger.info(f"  Settings keys: {list(settings.keys())}")

        return settings

    def _get_nested_value(self, data: dict[str, Any], key: str) -> Any:
        """Get a value from nested dict using dot notation."""
        keys = key.split(".")
        current = data

        try:
            for k in keys:
                current = current[k]
            return current
        except (KeyError, TypeError):
            return None

    async def get_guild_roles(self, guild_id: int) -> dict[str, int]:
        """
        Get role configuration for a guild.

        Returns:
            Dict mapping role names to Discord role IDs
        """
        roles = {}

        # Standard role mappings - already normalized to int at load time
        role_keys = [
            "bot_verified_role_id",
            "main_role_id",
            "affiliate_role_id",
            "non_member_role_id",
        ]

        for role_key in role_keys:
            # bot_verified_role is stored as list in DB, handle specially
            if role_key == "bot_verified_role_id":
                role_ids = await self.get_guild_setting(
                    guild_id, "roles.bot_verified_role", []
                )
                if role_ids:
                    roles[role_key] = (
                        role_ids[0] if isinstance(role_ids, list) else role_ids
                    )
            else:
                # Other roles stored directly or as lists
                setting_key = role_key.replace("_id", "")
                role_ids = await self.get_guild_setting(
                    guild_id, f"roles.{setting_key}", []
                )
                if role_ids:
                    # Handle both list and single values
                    roles[role_key] = (
                        role_ids[0] if isinstance(role_ids, list) else role_ids
                    )

        # Admin roles (list) - already normalized to list[int]
        admin_roles = await self.get_guild_setting(guild_id, "roles.bot_admins", [])
        if admin_roles:
            roles["bot_admin_role_ids"] = admin_roles

        selectable_roles = await self.get_guild_setting(
            guild_id, "selectable_roles", []
        )
        if not selectable_roles:
            selectable_roles = self._global_config.get("selectable_roles", [])
        if selectable_roles:
            roles["selectable_roles"] = selectable_roles

        return roles

    async def get_guild_channels(self, guild_id: int) -> dict[str, int]:
        """
        Get channel configuration for a guild.

        Returns:
            Dict mapping channel names to Discord channel IDs
        """
        channels = {}

        channel_keys = [
            "verification_channel_id",
            "bot_spam_channel_id",
            "public_announcement_channel_id",
            "leadership_announcement_channel_id",
        ]

        for channel_key in channel_keys:
            channel_id = await self.get_guild_setting(
                guild_id, f"channels.{channel_key}"
            )
            if channel_id:
                channels[channel_key] = int(channel_id)

        return channels

    async def clear_guild_cache(self, guild_id: int) -> None:
        """Clear cached settings for a guild."""
        async with self._cache_lock:
            self._guild_cache.pop(guild_id, None)
            self._guild_versions.pop(guild_id, None)

        self.logger.debug(f"Cleared cache for guild {guild_id}")

    async def maybe_refresh_guild(self, guild_id: int, force: bool = False) -> bool:
        """Reload guild settings if the version marker changed."""
        if force:
            await self.clear_guild_cache(guild_id)
            await self._get_guild_settings(guild_id)
            return True

        db_version = await self._fetch_settings_version_from_db(guild_id)
        async with self._cache_lock:
            cached_version = self._guild_versions.get(guild_id)

        if db_version == cached_version:
            return False

        await self.clear_guild_cache(guild_id)
        await self._get_guild_settings(guild_id)
        return True

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the config service."""
        base_health = await super().health_check()

        return {
            **base_health,
            "global_config_loaded": bool(self._global_config),
            "cached_guilds": len(self._guild_cache),
        }

    async def add_guild_jtc_channel(self, guild_id: int, channel_id: int) -> None:
        """
        Add a join-to-create channel for a guild.

        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to add as JTC
        """
        self._ensure_initialized()

        existing = await self.get_guild_setting(guild_id, "voice.jtc_channels", [])
        if not isinstance(existing, list):
            existing = []

        # Add new channel if not already present
        if channel_id not in existing:
            existing.append(channel_id)
            await self.set_guild_setting(guild_id, "voice.jtc_channels", existing)
            self.logger.info(f"Added JTC channel {channel_id} to guild {guild_id}")

    async def remove_guild_jtc_channel(self, guild_id: int, channel_id: int) -> None:
        """
        Remove a join-to-create channel for a guild.

        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to remove from JTC list
        """
        self._ensure_initialized()

        # Get existing JTC channels
        existing = await self.get_guild_setting(guild_id, "voice.jtc_channels", [])
        if not isinstance(existing, list):
            return

        # Remove channel if present
        if channel_id in existing:
            existing.remove(channel_id)
            await self.set_guild_setting(guild_id, "voice.jtc_channels", existing)
            self.logger.info(f"Removed JTC channel {channel_id} from guild {guild_id}")

    async def get_guild_jtc_channels(self, guild_id: int) -> list[int]:
        """
        Get all join-to-create channels for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of voice channel IDs configured as JTC channels
        """
        channels = await self.get_guild_setting(guild_id, "voice.jtc_channels", [])
        if not isinstance(channels, list):
            return []
        return [int(c) for c in channels]

    def _extract_version_value(self, raw_value: Any) -> str | None:
        """Extract a comparable version string from stored metadata."""
        if raw_value is None:
            return None
        if isinstance(raw_value, dict):
            candidate = raw_value.get("version") or raw_value.get("updated_at")
            return str(candidate) if candidate else None
        if isinstance(raw_value, str):
            return raw_value
        return None

    async def _fetch_settings_version_from_db(self, guild_id: int) -> str | None:
        row = await BaseRepository.fetch_one(
            """
            SELECT value FROM guild_settings
            WHERE guild_id = ? AND key = ?
            """,
            (guild_id, SETTINGS_VERSION_KEY),
        )

        if not row:
            return None

        try:
            payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except (json.JSONDecodeError, TypeError):
            return None

        return self._extract_version_value(payload)

    def get_config(self) -> dict[str, Any]:
        """
        Get the global configuration dictionary.

        Returns:
            Global configuration dictionary
        """
        self._ensure_initialized()
        return self._global_config.copy()

    async def get_join_to_create_channels(self, guild_id: int) -> list[int]:
        """
        Alias for get_guild_jtc_channels for backward compatibility.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of join-to-create channel IDs
        """
        return await self.get_guild_jtc_channels(guild_id)

    # -------------------------------------------------------------------------
    # Type-Safe Configuration Accessors
    # -------------------------------------------------------------------------
    # These methods provide a uniform, typed interface for common config values,
    # eliminating scattered get() calls with hardcoded key strings.

    async def get_org_sid(self, guild_id: int, default: str = "TEST") -> str:
        """Get the organization SID for a guild."""
        value = await self.get(guild_id, CONFIG_ORG_SID, default=default)
        return str(value) if value else default

    async def get_org_name(self, guild_id: int, default: str = "") -> str:
        """Get the organization name for a guild."""
        value = await self.get(guild_id, CONFIG_ORG_NAME, default=default)
        return str(value) if value else default

    async def get_verified_role_id(self, guild_id: int) -> int | None:
        """Get the verified role ID for a guild."""
        value = await self.get(guild_id, CONFIG_VERIFIED_ROLE)
        return self._parse_first_role_id(value)

    async def get_main_role_id(self, guild_id: int) -> int | None:
        """Get the main member role ID for a guild."""
        value = await self.get(guild_id, CONFIG_MAIN_ROLE)
        return self._parse_first_role_id(value)

    async def get_affiliate_role_id(self, guild_id: int) -> int | None:
        """Get the affiliate role ID for a guild."""
        value = await self.get(guild_id, CONFIG_AFFILIATE_ROLE)
        return self._parse_first_role_id(value)

    async def get_nonmember_role_id(self, guild_id: int) -> int | None:
        """Get the non-member role ID for a guild."""
        value = await self.get(guild_id, CONFIG_NONMEMBER_ROLE)
        return self._parse_first_role_id(value)

    async def get_bot_admin_role_ids(self, guild_id: int) -> list[int]:
        """Get the bot admin role IDs for a guild."""
        value = await self.get(guild_id, CONFIG_BOT_ADMINS, default=[])
        return self._parse_role_id_list(value)

    async def get_discord_manager_role_ids(self, guild_id: int) -> list[int]:
        """Get the Discord manager role IDs for a guild."""
        value = await self.get(guild_id, CONFIG_DISCORD_MANAGERS, default=[])
        return self._parse_role_id_list(value)

    async def get_moderator_role_ids(self, guild_id: int) -> list[int]:
        """Get the moderator role IDs for a guild."""
        value = await self.get(guild_id, CONFIG_MODERATORS, default=[])
        return self._parse_role_id_list(value)

    async def get_staff_role_ids(self, guild_id: int) -> list[int]:
        """Get the staff role IDs for a guild."""
        value = await self.get(guild_id, CONFIG_STAFF, default=[])
        return self._parse_role_id_list(value)

    async def get_verification_channel_id(self, guild_id: int) -> int | None:
        """Get the verification channel ID for a guild."""
        value = await self.get(guild_id, CONFIG_VERIFICATION_CHANNEL)
        return self._safe_int(value)

    async def get_bot_spam_channel_id(self, guild_id: int) -> int | None:
        """Get the bot spam channel ID for a guild."""
        value = await self.get(guild_id, CONFIG_BOT_SPAM_CHANNEL)
        return self._safe_int(value)

    async def get_public_announcement_channel_id(self, guild_id: int) -> int | None:
        """Get the public announcement channel ID for a guild."""
        value = await self.get(guild_id, CONFIG_PUBLIC_ANNOUNCE_CHANNEL)
        return self._safe_int(value)

    async def get_leadership_announcement_channel_id(self, guild_id: int) -> int | None:
        """Get the leadership announcement channel ID for a guild."""
        value = await self.get(guild_id, CONFIG_LEADERSHIP_ANNOUNCE_CHANNEL)
        return self._safe_int(value)

    # -------------------------------------------------------------------------
    # Helper Methods for Type-Safe Accessors
    # -------------------------------------------------------------------------

    def _safe_int(self, value: Any) -> int | None:
        """Safely convert a value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_first_role_id(self, value: Any) -> int | None:
        """Parse a role value that might be a single ID or list, returning first ID."""
        if value is None:
            return None
        if isinstance(value, list):
            return self._safe_int(value[0]) if value else None
        return self._safe_int(value)

    def _parse_role_id_list(self, value: Any) -> list[int]:
        """Parse a value into a list of role IDs."""
        if not value:
            return []
        if not isinstance(value, list):
            value = [value]
        result = []
        for v in value:
            parsed = self._safe_int(v)
            if parsed is not None:
                result.append(parsed)
        return result

