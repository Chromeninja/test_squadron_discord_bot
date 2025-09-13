"""
Guild service for managing guild-specific operations and state.
"""

import asyncio
from typing import Any

import discord

from services.db.database import Database

from .base import BaseService
from .config_service import ConfigService


class GuildService(BaseService):
    """
    Service for managing guild-specific operations and maintaining guild state.

    Handles guild registration, role caching, permission checking, and
    multi-guild coordination.
    """

    def __init__(self, config_service: ConfigService) -> None:
        super().__init__("guild")
        self.config_service = config_service
        self._role_cache: dict[int, dict[int, discord.Role]] = {}
        self._missing_role_warnings: dict[int, set[int]] = {}
        self._cache_lock = asyncio.Lock()

    async def _initialize_impl(self) -> None:
        """Initialize guild service."""
        await self._ensure_guild_tables()

    async def _ensure_guild_tables(self) -> None:
        """Ensure guild-related database tables exist."""
        async with Database.get_connection() as db:
            # Guild registration table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_registry (
                    guild_id INTEGER PRIMARY KEY,
                    guild_name TEXT NOT NULL,
                    registered_at INTEGER DEFAULT (strftime('%s','now')),
                    last_seen INTEGER DEFAULT (strftime('%s','now')),
                    is_active INTEGER DEFAULT 1
                )
            """)

            # Guild-specific rate limits
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_rate_limits (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 1,
                    window_start INTEGER DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (guild_id, user_id, action_type)
                )
            """)

            await db.commit()

    async def register_guild(self, guild: discord.Guild) -> None:
        """
        Register a guild in the database and cache roles.

        Args:
            guild: Discord guild to register
        """
        self._ensure_initialized()

        async with Database.get_connection() as db:
            await db.execute("""
                INSERT OR REPLACE INTO guild_registry
                (guild_id, guild_name, last_seen, is_active)
                VALUES (?, ?, strftime('%s','now'), 1)
            """, (guild.id, guild.name))
            await db.commit()

        await self.cache_guild_roles(guild)

        self.logger.info(f"Registered guild: {guild.name} ({guild.id})")

    async def cache_guild_roles(self, guild: discord.Guild) -> None:
        """
        Cache important roles for a guild.

        Args:
            guild: Discord guild to cache roles for
        """
        self._ensure_initialized()

        # Get role configuration for this guild
        role_config = await self.config_service.get_guild_roles(guild.id)

        cached_roles = {}
        missing_roles = set()

        # Cache individual roles
        for _role_key, role_id in role_config.items():
            if isinstance(role_id, list):
                # Handle role lists (admin roles, etc.)
                for rid in role_id:
                    role = guild.get_role(rid)
                    if role:
                        cached_roles[rid] = role
                    else:
                        missing_roles.add(rid)
            else:
                # Handle single roles
                role = guild.get_role(role_id)
                if role:
                    cached_roles[role_id] = role
                else:
                    missing_roles.add(role_id)

        async with self._cache_lock:
            self._role_cache[guild.id] = cached_roles
            self._missing_role_warnings[guild.id] = missing_roles

        # Log missing roles (but only once per guild per restart)
        if missing_roles:
            # Check if we've already reported missing roles for this guild
            reported = await self._has_reported_missing_roles(guild.id)
            if not reported:
                self.logger.warning(
                    f"Missing roles in guild {guild.name}: {missing_roles}"
                )
                await self._mark_reported_missing_roles(guild.id)

        self.logger.debug(f"Cached {len(cached_roles)} roles for guild {guild.name}")

    async def get_cached_role(
        self,
        guild_id: int,
        role_id: int
    ) -> discord.Role | None:
        """
        Get a cached role by ID.

        Args:
            guild_id: Discord guild ID
            role_id: Discord role ID

        Returns:
            Cached role or None if not found
        """
        self._ensure_initialized()

        async with self._cache_lock:
            guild_roles = self._role_cache.get(guild_id, {})
            return guild_roles.get(role_id)

    async def has_admin_role(
        self,
        member: discord.Member
    ) -> bool:
        """
        Check if a member has admin privileges in their guild.

        Args:
            member: Discord member to check

        Returns:
            True if member has admin role
        """
        self._ensure_initialized()

        # Get admin role IDs for this guild
        admin_roles = await self.config_service.get_guild_setting(
            member.guild.id, "roles.bot_admins", []
        )
        lead_mod_roles = await self.config_service.get_guild_setting(
            member.guild.id, "roles.lead_moderators", []
        )

        all_admin_roles = set(admin_roles + lead_mod_roles)
        member_role_ids = {role.id for role in member.roles}

        return bool(all_admin_roles & member_role_ids)

    async def check_guild_permissions(
        self,
        guild: discord.Guild
    ) -> dict[str, bool]:
        """
        Check bot permissions in a guild.

        Args:
            guild: Discord guild to check

        Returns:
            Dict mapping permission names to boolean values
        """
        required_permissions = [
            "manage_roles",
            "manage_channels",
            "change_nickname",
            "manage_nicknames",
            "view_channel",
            "send_messages",
            "embed_links",
            "read_message_history",
            "use_application_commands",
            "connect",
            "move_members",
        ]

        if not guild.me:
            return dict.fromkeys(required_permissions, False)

        bot_perms = guild.me.guild_permissions
        return {
            perm: getattr(bot_perms, perm, False)
            for perm in required_permissions
        }

    async def get_active_guilds(self) -> list[int]:
        """
        Get list of active guild IDs.

        Returns:
            List of guild IDs that are active
        """
        self._ensure_initialized()

        async with Database.get_connection() as db, db.execute(
            "SELECT guild_id FROM guild_registry WHERE is_active = 1"
        ) as cursor:
            return [row[0] async for row in cursor]

    async def update_guild_activity(self, guild_id: int) -> None:
        """
        Update the last seen timestamp for a guild.

        Args:
            guild_id: Discord guild ID
        """
        async with Database.get_connection() as db:
            await db.execute("""
                UPDATE guild_registry
                SET last_seen = strftime('%s','now')
                WHERE guild_id = ?
            """, (guild_id,))
            await db.commit()

    async def deactivate_guild(self, guild_id: int) -> None:
        """
        Mark a guild as inactive (bot was removed).

        Args:
            guild_id: Discord guild ID
        """
        async with Database.get_connection() as db:
            await db.execute("""
                UPDATE guild_registry
                SET is_active = 0, last_seen = strftime('%s','now')
                WHERE guild_id = ?
            """, (guild_id,))
            await db.commit()

        # Clear cache for this guild
        async with self._cache_lock:
            self._role_cache.pop(guild_id, None)
            self._missing_role_warnings.pop(guild_id, None)

        self.logger.info(f"Deactivated guild {guild_id}")

    async def _has_reported_missing_roles(self, guild_id: int) -> bool:
        """Check if we've already reported missing roles for a guild."""
        async with Database.get_connection() as db, db.execute("""
                SELECT 1 FROM guild_settings
                WHERE guild_id = ? AND key = 'missing_roles_reported'
            """, (guild_id,)) as cursor:
            return bool(await cursor.fetchone())

    async def _mark_reported_missing_roles(self, guild_id: int) -> None:
        """Mark that we've reported missing roles for a guild."""
        await self.config_service.set_guild_setting(
            guild_id, "missing_roles_reported", True
        )

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the guild service."""
        base_health = await super().health_check()

        async with self._cache_lock:
            cached_guilds = len(self._role_cache)
            total_cached_roles = sum(len(roles) for roles in self._role_cache.values())

        return {
            **base_health,
            "cached_guilds": cached_guilds,
            "total_cached_roles": total_cached_roles,
        }
