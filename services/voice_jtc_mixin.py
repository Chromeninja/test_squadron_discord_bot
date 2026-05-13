"""
VoiceJtcMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

from typing import Any

import discord  # type: ignore[import-not-found]

from services.db.repository import BaseRepository
from services.voice_base_mixin import VoiceServiceBase
from utils.types import VoiceChannelResult


class VoiceJtcMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def initialize_guild_voice_channels(self, guild_id: int) -> None:
        """
        Initialize voice channel settings for a guild.

        Validates that configured join-to-create (JTC) channels exist in the guild.
        Logs warnings for missing channels but does not create them automatically.

        Args:
            guild_id: Discord guild ID to initialize voice channels for
        """
        self.logger.info(f"Initializing voice channels for guild {guild_id}")

        if not self.bot:
            self.logger.warning(
                f"Bot instance not available for guild {guild_id} voice initialization"
            )
            return

        # Get the guild object
        guild = self.bot.get_guild(guild_id)
        if not guild:
            self.logger.warning(
                f"Guild {guild_id} not found for voice channel initialization"
            )
            return

        try:
            # Get configured JTC channels for this guild
            jtc_channel_ids = await self._get_guild_jtc_channels(guild_id)

            if not jtc_channel_ids:
                self.logger.info(
                    f"No JTC channels configured for guild {guild.name} ({guild_id})"
                )
                return

            # Validate each configured JTC channel exists
            missing_channels = []
            existing_channels = []

            for channel_id in jtc_channel_ids:
                channel = guild.get_channel(channel_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    existing_channels.append(channel_id)
                else:
                    missing_channels.append(channel_id)

            # Log results
            if existing_channels:
                self.logger.info(
                    f"Found {len(existing_channels)} valid JTC channels in guild {guild.name}"
                )

            if missing_channels:
                self.logger.warning(
                    f"Missing {len(missing_channels)} configured JTC channels in guild {guild.name}: {missing_channels}"
                )

            self.logger.info(
                f"Voice channel initialization completed for guild {guild.name} ({guild_id})"
            )

        except Exception as e:
            self.logger.exception(
                f"Error initializing voice channels for guild {guild_id}", exc_info=e
            )

    async def _get_guild_jtc_channels(self, guild_id: int) -> list[int]:
        """Get join-to-create channel IDs for a guild."""
        try:
            return await self.config_service.get_guild_jtc_channels(guild_id)
        except Exception as e:
            self.logger.exception("Error getting JTC channels", exc_info=e)
            return []

    async def _load_channel_settings(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """
        Load saved channel settings for a user from the database.

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            user_id: Discord user ID

        Returns:
            Dictionary of settings or None if no settings exist
        """
        try:
            if self.debug_logging_enabled:
                self.logger.debug(
                    "Loading channel settings for user %s in guild %s, JTC %s",
                    user_id,
                    guild_id,
                    jtc_channel_id,
                )
            row = await BaseRepository.fetch_one(
                """
                SELECT channel_name, user_limit, lock
                FROM channel_settings
                WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                (guild_id, jtc_channel_id, user_id),
            )

            if not row:
                if self.debug_logging_enabled:
                    self.logger.debug(
                        "No settings row found for user %s, guild %s, JTC %s",
                        user_id,
                        guild_id,
                        jtc_channel_id,
                    )
                return None

            channel_name, user_limit, lock = row
            result = {
                "channel_name": channel_name,
                "user_limit": user_limit,
                "lock": lock,
            }
            if self.debug_logging_enabled:
                self.logger.debug("Found settings: %s", result)
            return result

        except Exception as e:
            self.logger.exception("Error loading channel settings", exc_info=e)
            return None

    async def get_user_channel_settings(
        self, guild_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """
        Get all settings for a user's voice channel.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Dictionary of settings or None if no settings exist
        """
        try:
            rows = await BaseRepository.fetch_all(
                """
                SELECT setting_key, setting_value
                FROM voice_channel_settings
                WHERE guild_id = ? AND owner_id = ?
                """,
                (guild_id, user_id),
            )

            if not rows:
                return None

            return {row[0]: row[1] for row in rows}

        except Exception as e:
            self.logger.exception("Error getting user channel settings", exc_info=e)
            return None

    async def create_settings_list_embed(
        self, guild_id: int, user_id: int, settings: dict[str, Any]
    ) -> discord.Embed:
        """
        Create an embed showing a user's voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            settings: Settings dictionary

        Returns:
            Discord embed with formatted settings
        """
        embed = discord.Embed(
            title="🎙️ Your Voice Channel Settings", color=discord.Color.blue()
        )

        if not settings:
            embed.description = "No custom settings configured."
            return embed

        # Format settings nicely
        settings_text = []
        for key, value in settings.items():
            formatted_key = key.replace("_", " ").title()
            settings_text.append(f"**{formatted_key}:** {value}")

        embed.add_field(
            name="Current Settings",
            value="\n".join(settings_text) if settings_text else "None",
            inline=False,
        )

        return embed

    async def _perform_ownership_transfer(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        new_owner_id: int,
        previous_owner_id: int,
        guild_id: int,
        jtc_channel_id: int,
    ) -> VoiceChannelResult:
        """Shared helper that performs the DB ownership transfer and Discord
        permission update.  Both *claim* and *transfer* delegate here so the
        two code-paths stay in sync.

        Args:
            channel: The voice/stage channel whose ownership is changing.
            new_owner_id: Discord user ID of the incoming owner.
            previous_owner_id: Discord user ID of the outgoing owner (or the
                effective previous owner for orphaned channels).
            guild_id: Discord guild ID.
            jtc_channel_id: The join-to-create channel that spawned *channel*.

        Returns:
            VoiceChannelResult with success/failure status.
        """
        from helpers.permissions_helper import update_channel_owner
        from helpers.voice_repo import transfer_channel_owner

        success = await transfer_channel_owner(
            voice_channel_id=channel.id,
            new_owner_id=new_owner_id,
            guild_id=guild_id,
            jtc_channel_id=jtc_channel_id,
        )

        if not success:
            return VoiceChannelResult(success=False, error="DB_TEMP_ERROR")

        await update_channel_owner(
            channel=channel,
            new_owner_id=new_owner_id,
            previous_owner_id=previous_owner_id,
            guild_id=guild_id,
            jtc_channel_id=jtc_channel_id,
        )

        return VoiceChannelResult(
            success=True, channel_id=channel.id, channel_mention=channel.mention
        )

    async def claim_voice_channel(
        self, guild_id: int, user_id: int, user: discord.Member
    ) -> VoiceChannelResult:
        """
        Claim ownership of a voice channel if the current owner is absent.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            user: Discord member object

        Returns:
            VoiceChannelResult with success status and error code (not formatted message)
        """
        try:
            # Check if user is in a voice channel
            if not user.voice or not user.voice.channel:
                return VoiceChannelResult(
                    success=False,
                    error="NOT_IN_VOICE",
                )

            channel = user.voice.channel

            # Check if this is a managed voice channel from voice_channels
            row = await BaseRepository.fetch_one(
                """
                SELECT owner_id, previous_owner_id, jtc_channel_id
                FROM voice_channels
                WHERE guild_id = ? AND voice_channel_id = ? AND is_active = 1
                """,
                (guild_id, channel.id),
            )

            if not row:
                return VoiceChannelResult(success=False, error="NOT_MANAGED")

            current_owner_id, previous_owner_id, jtc_channel_id = row
            ownerless = current_owner_id == self.ORPHAN_OWNER_ID
            effective_previous_owner = (
                previous_owner_id
                if ownerless and previous_owner_id
                else current_owner_id
            )

            # Check if current owner is still in the channel (skip for orphaned channels)
            if not ownerless:
                current_owner = channel.guild.get_member(current_owner_id)
                if current_owner and current_owner in channel.members:
                    return VoiceChannelResult(
                        success=False,
                        error="OWNER_PRESENT",
                    )

            return await self._perform_ownership_transfer(
                channel=channel,
                new_owner_id=user_id,
                previous_owner_id=effective_previous_owner,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )

        except Exception as e:
            self.logger.exception("Error claiming voice channel", exc_info=e)
            return VoiceChannelResult(success=False, error="UNKNOWN")

    async def transfer_voice_channel_ownership(
        self,
        guild_id: int,
        current_owner_id: int,
        new_owner_id: int,
        new_owner: discord.Member,
    ) -> VoiceChannelResult:
        """
        Transfer ownership of a voice channel to another user.

        Args:
            guild_id: Discord guild ID
            current_owner_id: Current owner's user ID
            new_owner_id: New owner's user ID
            new_owner: New owner member object

        Returns:
            VoiceChannelResult with success status and error code (not formatted message)
        """
        try:
            # Find the user's voice channel from voice_channels table
            row = await BaseRepository.fetch_one(
                """
                SELECT voice_channel_id, jtc_channel_id FROM voice_channels
                WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (guild_id, current_owner_id),
            )

            if not row:
                return VoiceChannelResult(success=False, error="NO_CHANNEL")

            voice_channel_id, jtc_channel_id = row

            # Check if new owner is in the channel
            channel = discord.utils.get(
                new_owner.guild.voice_channels, id=voice_channel_id
            )
            if not channel or new_owner not in channel.members:
                return VoiceChannelResult(
                    success=False,
                    error="NOT_IN_CHANNEL",
                )

            return await self._perform_ownership_transfer(
                channel=channel,
                new_owner_id=new_owner_id,
                previous_owner_id=current_owner_id,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )

        except Exception as e:
            self.logger.exception(
                "Error transferring voice channel ownership", exc_info=e
            )
            return VoiceChannelResult(success=False, error="UNKNOWN")

    async def get_all_voice_channels(self, guild_id: int) -> list[dict[str, Any]]:
        """
        Get all managed voice channels for a guild from voice_channels table.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of channel information dictionaries with owner_id, voice_channel_id, created_at
        """
        try:
            rows = await BaseRepository.fetch_all(
                """
                SELECT owner_id, voice_channel_id, created_at
                FROM voice_channels
                WHERE guild_id = ? AND is_active = 1
                ORDER BY created_at DESC
                """,
                (guild_id,),
            )

            channels = [
                {
                    "owner_id": row[0],
                    "voice_channel_id": row[1],
                    "created_at": row[2],
                }
                for row in rows
            ]

            # Filter by in-memory cache to ensure channels are still active
            # Fall back to database if cache is not available/reliable
            if self.managed_voice_channels:
                active_channels = [
                    channel
                    for channel in channels
                    if channel["voice_channel_id"] in self.managed_voice_channels
                ]
                # If cache filtering results in significantly fewer channels,
                # use database as authoritative source and update cache
                if len(active_channels) < len(channels) * 0.5:
                    self.logger.info(
                        f"Cache appears stale, using database as source of truth for {guild_id}"
                    )
                    # Refresh cache from database
                    for channel in channels:
                        self.managed_voice_channels.add(channel["voice_channel_id"])
                    return channels
                return active_channels
            else:
                # No cache available, use database as source of truth
                self.logger.info(
                    f"No cache available, using database as source of truth for {guild_id}"
                )
                for channel in channels:
                    self.managed_voice_channels.add(channel["voice_channel_id"])
                return channels

        except Exception as e:
            self.logger.exception("Error getting all voice channels", exc_info=e)
            return []

