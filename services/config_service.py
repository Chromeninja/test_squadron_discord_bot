"""
Configuration service for per-guild settings and global configuration.
"""

import asyncio
from typing import Any

import yaml

from services.db.database import Database

from .base import BaseService


class ConfigService(BaseService):
    """
    Service for managing per-guild configuration and global settings.
    
    Provides a clean interface for accessing guild-specific settings while
    falling back to global defaults.
    """

    def __init__(self) -> None:
        super().__init__("config")
        self._global_config: dict[str, Any] = {}
        self._guild_cache: dict[int, dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()

    async def _initialize_impl(self) -> None:
        """Load global configuration."""
        await self._load_global_config()

    async def _load_global_config(self) -> None:
        """Load global configuration from config.yaml."""
        try:
            with open("config/config.yaml", encoding="utf-8") as f:
                self._global_config = yaml.safe_load(f) or {}
            self.logger.info("Global configuration loaded successfully")
        except FileNotFoundError:
            self.logger.warning("Global config file not found, using empty config")
            self._global_config = {}
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing global config: {e}")
            self._global_config = {}

    async def get_guild_setting(
        self,
        guild_id: int,
        key: str,
        default: Any = None
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

    async def set_guild_setting(
        self,
        guild_id: int,
        key: str,
        value: Any
    ) -> None:
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
        async with Database.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
                """,
                (guild_id, key, json.dumps(value))
            )
            await db.commit()

        # Update cache
        async with self._cache_lock:
            if guild_id not in self._guild_cache:
                self._guild_cache[guild_id] = {}
            self._guild_cache[guild_id][key] = value

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
                return self._guild_cache[guild_id]

        # Load from database
        settings = {}
        async with Database.get_connection() as db:
            async with db.execute(
                "SELECT key, value FROM guild_settings WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                async for row in cursor:
                    key, value_json = row
                    try:
                        import json
                        settings[key] = json.loads(value_json)
                    except (json.JSONDecodeError, TypeError):
                        self.logger.warning(
                            f"Failed to parse setting {key} for guild {guild_id}"
                        )

        # Cache the settings
        async with self._cache_lock:
            self._guild_cache[guild_id] = settings

        return settings

    def _get_nested_value(self, data: dict[str, Any], key: str) -> Any:
        """Get a value from nested dict using dot notation."""
        keys = key.split('.')
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

        # Standard role mappings
        role_keys = [
            "bot_verified_role_id",
            "main_role_id",
            "affiliate_role_id",
            "non_member_role_id"
        ]

        for role_key in role_keys:
            role_id = await self.get_guild_setting(guild_id, f"roles.{role_key}")
            if role_id:
                roles[role_key] = int(role_id)

        # Admin roles (list)
        admin_roles = await self.get_guild_setting(guild_id, "roles.bot_admins", [])
        if admin_roles:
            roles["bot_admin_role_ids"] = [int(r) for r in admin_roles]

        # Lead moderator roles (list)
        lead_mod_roles = await self.get_guild_setting(
            guild_id, "roles.lead_moderators", []
        )
        if lead_mod_roles:
            roles["lead_moderator_role_ids"] = [int(r) for r in lead_mod_roles]

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
            "leadership_announcement_channel_id"
        ]

        for channel_key in channel_keys:
            channel_id = await self.get_guild_setting(guild_id, f"channels.{channel_key}")
            if channel_id:
                channels[channel_key] = int(channel_id)

        return channels

    async def clear_guild_cache(self, guild_id: int) -> None:
        """Clear cached settings for a guild."""
        async with self._cache_lock:
            self._guild_cache.pop(guild_id, None)

        self.logger.debug(f"Cleared cache for guild {guild_id}")

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the config service."""
        base_health = await super().health_check()

        return {
            **base_health,
            "global_config_loaded": bool(self._global_config),
            "cached_guilds": len(self._guild_cache),
        }

    async def maybe_migrate_legacy_settings(self, bot) -> None:
        """
        Placeholder for legacy settings migration.
        
        This method is called during bot startup to migrate any legacy
        configuration formats to the new service-based structure.
        """
        self.logger.info("Legacy settings migration - no migration needed")

    async def add_guild_jtc_channel(self, guild_id: int, channel_id: int) -> None:
        """
        Add a join-to-create channel for a guild.
        
        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to add as JTC
        """
        self._ensure_initialized()

        # Get existing JTC channels
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
