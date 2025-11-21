"""
Unified configuration helper for guild-aware Discord settings.

This service provides high-level configuration access with Discord object resolution,
validation, and consistent error handling. It wraps ConfigService to provide a clean
interface for accessing channels, roles, and other Discord-related settings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord.ext import commands

    from services.config_service import ConfigService

logger = logging.getLogger(__name__)


class GuildConfigHelper:
    """
    High-level configuration access for Discord guilds.

    Provides methods to fetch configured channels, roles, and settings with:
    - Automatic ConfigService integration
    - Discord object resolution (IDs → Channel/Role objects)
    - Validation and error logging
    - Fallback to global defaults
    """

    def __init__(self, bot: commands.Bot, config_service: ConfigService) -> None:
        """
        Initialize guild config helper.

        Args:
            bot: Discord bot instance for object resolution
            config_service: Configuration service for settings retrieval
        """
        self.bot = bot
        self.config = config_service

    async def get_channel(
        self,
        guild_id: int,
        channel_key: str,
        guild: discord.Guild | None = None,
    ) -> discord.TextChannel | None:
        """
        Get a configured text channel by key.

        Args:
            guild_id: Discord guild ID
            channel_key: Channel configuration key
                (e.g., "leadership_log", "admin_recheck")
            guild: Optional guild object (fetched if not provided)

        Returns:
            TextChannel object if found and valid, None otherwise
        """
        channel_id = await self.config.get(
            guild_id, f"channels.{channel_key}", parser=int
        )
        if not channel_id:
            logger.debug(f"No channel configured for {channel_key} in guild {guild_id}")
            return None

        if guild is None:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                logger.warning(
                    f"Guild {guild_id} not found when fetching "
                    f"channel {channel_key}"
                )
                return None

        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(
                f"Channel {channel_id} ({channel_key}) not found in guild {guild_id}"
            )
            return None

        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                f"Channel {channel_id} ({channel_key}) is not a text "
                f"channel in guild {guild_id}"
            )
            return None

        return channel

    async def get_leadership_log_channel(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> discord.TextChannel | None:
        """Get the leadership log channel for announcements."""
        return await self.get_channel(guild_id, "leadership_log", guild)

    async def get_admin_recheck_channel(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> discord.TextChannel | None:
        """Get admin recheck notification channel."""
        return await self.get_channel(guild_id, "admin_recheck", guild)

    async def get_role(
        self, guild_id: int, role_key: str, guild: discord.Guild | None = None
    ) -> discord.Role | None:
        """
        Get a configured role by key.

        Args:
            guild_id: Discord guild ID
            role_key: Role configuration key
                (e.g., "bot_verified_role_id", "main_role_id")
            guild: Optional guild object (fetched if not provided)

        Returns:
            Role object if found and valid, None otherwise
        """
        role_id = await self.config.get(guild_id, f"roles.{role_key}", parser=int)
        if not role_id:
            logger.debug(f"No role configured for {role_key} in guild {guild_id}")
            return None

        if guild is None:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                logger.warning(
                    f"Guild {guild_id} not found when fetching "
                    f"role {role_key}"
                )
                return None

        role = guild.get_role(role_id)
        if not role:
            logger.warning(f"Role {role_id} ({role_key}) not found in guild {guild_id}")
            return None

        return role

    async def get_admin_roles(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> list[discord.Role]:
        """
        Get all configured admin roles.

        Args:
            guild_id: Discord guild ID
            guild: Optional guild object (fetched if not provided)

        Returns:
            List of Role objects (empty if none configured or found)
        """
        role_ids = await self.config.get(guild_id, "roles.bot_admins", default=[])
        if not role_ids:
            logger.debug(f"No admin roles configured for guild {guild_id}")
            return []

        if guild is None:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                logger.warning(
                    f"Guild {guild_id} not found when fetching admin roles"
                )
                return []

        roles = []
        for role_id in role_ids:
            try:
                rid = int(role_id)
                role = guild.get_role(rid)
                if role:
                    roles.append(role)
                else:
                    logger.warning(
                        f"Admin role {rid} not found in guild {guild_id}"
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f"Invalid admin role ID: {role_id} in guild {guild_id}"
                )

        return roles

    async def get_lead_moderator_roles(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> list[discord.Role]:
        """
        Get all configured lead moderator roles.

        Args:
            guild_id: Discord guild ID
            guild: Optional guild object (fetched if not provided)

        Returns:
            List of Role objects (empty if none configured or found)
        """
        role_ids = await self.config.get(guild_id, "roles.lead_moderators", default=[])
        if not role_ids:
            logger.debug(f"No lead moderator roles configured for guild {guild_id}")
            return []

        if guild is None:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                logger.warning(
                    f"Guild {guild_id} not found when fetching "
                    f"lead moderator roles"
                )
                return []

        roles = []
        for role_id in role_ids:
            try:
                rid = int(role_id)
                role = guild.get_role(rid)
                if role:
                    roles.append(role)
                else:
                    logger.warning(
                        f"Lead moderator role {rid} not found in "
                        f"guild {guild_id}"
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f"Invalid lead moderator role ID: {role_id} in "
                    f"guild {guild_id}"
                )

        return roles

    async def get_verified_role(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> discord.Role | None:
        """Get the verified member role."""
        return await self.get_role(guild_id, "bot_verified_role_id", guild)

    async def get_main_role(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> discord.Role | None:
        """Get the main organization member role."""
        return await self.get_role(guild_id, "main_role_id", guild)

    async def get_affiliate_role(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> discord.Role | None:
        """Get the affiliate member role."""
        return await self.get_role(guild_id, "affiliate_role_id", guild)

    async def get_non_member_role(
        self, guild_id: int, guild: discord.Guild | None = None
    ) -> discord.Role | None:
        """Get the non-member role."""
        return await self.get_role(guild_id, "non_member_role_id", guild)

    async def get_setting(
        self,
        guild_id: int,
        setting_key: str,
        default: Any = None,
        parser: Callable[[Any], Any] | None = None,
    ) -> Any:
        """
        Get a raw configuration setting.

        Args:
            guild_id: Discord guild ID
            setting_key: Configuration key (supports dot notation)
            default: Default value if not found
            parser: Optional parser function (e.g., int, float)

        Returns:
            Configuration value or default
        """
        return await self.config.get(
            guild_id, setting_key, default=default, parser=parser
        )

    async def get_rate_limit_config(self, guild_id: int) -> dict[str, int]:
        """
        Get rate limiting configuration.

        Returns:
            Dict with keys: rate_limit_calls, rate_limit_period, rate_limit_bucket
        """
        return {
            "rate_limit_calls": await self.config.get(
                guild_id, "rate_limiting.calls", default=45, parser=int
            ),
            "rate_limit_period": await self.config.get(
                guild_id, "rate_limiting.period", default=60, parser=int
            ),
            "rate_limit_bucket": await self.config.get(
                guild_id, "rate_limiting.bucket", default=10, parser=int
            ),
        }

    async def get_username_404_threshold(self, guild_id: int) -> int:
        """
        Get the threshold for 404 username checks.

        Returns:
            Number of consecutive 404s before removing verified role
        """
        return await self.config.get(
            guild_id, "verification.username_404_threshold", default=5, parser=int
        )

    async def get_announcement_threshold(self, guild_id: int) -> int:
        """
        Get the threshold for announcement batching.

        Returns:
            Number of pending announcements before batch send
        """
        return await self.config.get(
            guild_id, "announcements.threshold", default=10, parser=int
        )

