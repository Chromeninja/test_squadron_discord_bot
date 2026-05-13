"""
VoiceChannelMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import discord  # type: ignore[import-not-found]

from helpers.discord_api import delete_channel
from services.db.repository import BaseRepository
from services.voice_base_mixin import VoiceServiceBase


class VoiceChannelMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def can_create_voice_channel(
        self,
        guild_id: int,
        jtc_channel_id: int,
        user_id: int,
        *,
        bypass_cooldown: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Check if a user can create a voice channel.

        For multi-channel support, we only check time-based cooldown,
        not whether the user already has an existing channel.

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            user_id: Discord user ID

        Returns:
            Tuple of (can_create, error_code_if_not) - returns error code, not formatted message
        """
        self._ensure_initialized()

        # Check if user is already in the process of creating a channel
        if self._is_user_creating(guild_id, user_id):
            if self.debug_logging_enabled:
                self.logger.debug(
                    "User %s is already creating a channel in guild %s",
                    user_id,
                    guild_id,
                )
            return False, "CREATING"

        # Only check time-based cooldown (removed existing channel check for multi-channel support)
        if not bypass_cooldown:
            cooldown_seconds = await self.config_service.get_guild_setting(
                guild_id, "voice.cooldown_seconds", 5
            )

            if await self._is_on_cooldown(
                guild_id, jtc_channel_id, user_id, cooldown_seconds
            ):
                return False, "COOLDOWN"

        return True, None

    async def delete_voice_channel(
        self, guild_id: int, voice_channel_id: int, reason: str = "Channel cleanup"
    ) -> bool:
        """
        Delete a voice channel and clean up database records.

        Args:
            guild_id: Discord guild ID
            voice_channel_id: Voice channel ID to delete
            reason: Reason for deletion

        Returns:
            True if deletion was successful
        """
        self._ensure_initialized()

        try:
            # Find channel record
            async with BaseRepository.transaction() as db:
                async with db.execute(
                    """
                    SELECT guild_id, jtc_channel_id, owner_id
                    FROM voice_channels
                    WHERE voice_channel_id = ? AND guild_id = ?
                """,
                    (voice_channel_id, guild_id),
                ) as cursor:
                    row = await cursor.fetchone()

                if not row:
                    self.logger.debug(
                        f"Voice channel {voice_channel_id} not found in database"
                    )
                    return False

                guild_id, _jtc_channel_id, _owner_id = row

                # Delete from Discord
                channel = self.bot.get_channel(voice_channel_id) if self.bot else None
                # Only delete if channel is a GuildChannel and not PrivateChannel/Thread
                if channel and isinstance(channel, discord.VoiceChannel):
                    result = await delete_channel(channel)
                    success = bool(result)
                else:
                    self.logger.warning(
                        f"Channel {voice_channel_id} is not a VoiceChannel or does not exist; skipping Discord deletion."
                    )
                    success = False

                # Clean up database records
                await self.cleanup_by_channel_id(voice_channel_id)

                self.logger.info(f"Deleted voice channel {voice_channel_id}: {reason}")
                return success

        except Exception as e:
            self.logger.exception(
                f"Failed to delete voice channel {voice_channel_id}: {e}"
            )
            return False

    async def handle_channel_deleted(self, guild_id: int, channel_id: int) -> None:
        """
        Handle when a voice channel is deleted externally (e.g., by Discord or manual deletion).

        Detects if deleted channel is a JTC channel and removes from config.
        Also cleans up any managed channels and database records.

        Args:
            guild_id: The guild ID where the channel was deleted
            channel_id: The ID of the deleted channel
        """
        self._ensure_initialized()

        try:
            # Check if this is a JTC channel
            is_jtc = await self._is_join_to_create_channel(guild_id, channel_id)

            if is_jtc:
                # This is a JTC channel deletion - remove from config and cleanup
                self.logger.info(
                    f"JTC channel {channel_id} deleted in guild {guild_id}, "
                    f"removing from config and cleaning up associated data"
                )

                cleanup_result = await self.remove_jtc_channel_from_config(
                    guild_id, channel_id, cleanup_managed=True
                )

                if not cleanup_result["success"]:
                    self.logger.warning(
                        f"Error removing JTC channel {channel_id} from config: "
                        f"{cleanup_result['error']}"
                    )
                else:
                    self.logger.info(
                        f"JTC channel {channel_id} removal complete: "
                        f"managed_cleanup={cleanup_result['managed_cleanup']}, "
                        f"db_purge={cleanup_result['db_purge']}"
                    )

            elif await self._is_managed_channel(channel_id):
                # This is a managed voice channel - clean up database records
                self.logger.info(
                    f"Cleaning up records for deleted managed channel {channel_id}"
                )
                await self._cleanup_empty_channel(channel_id)
            elif self.debug_logging_enabled:
                # Not a managed channel - log for reference
                self.logger.debug(
                    "Channel %s was not a managed voice channel", channel_id
                )

        except Exception as e:
            self.logger.exception(
                f"Error handling channel deletion for {channel_id}", exc_info=e
            )

    async def get_user_voice_channel(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> int | None:
        """
        Get the voice channel ID for a user in a specific JTC channel.

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            user_id: Discord user ID

        Returns:
            Voice channel ID or None if not found
        """
        return await BaseRepository.fetch_value(
            """
            SELECT voice_channel_id FROM voice_channels
            WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (guild_id, jtc_channel_id, user_id),
        )

    async def _get_any_user_voice_channel(
        self, guild_id: int, user_id: int
    ) -> int | None:
        """
        Get ANY existing voice channel ID for a user in a guild, regardless of which JTC created it.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Voice channel ID or None if not found
        """
        return await BaseRepository.fetch_value(
            """
            SELECT voice_channel_id FROM voice_channels
            WHERE guild_id = ? AND owner_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (guild_id, user_id),
        )

    async def cleanup_stale_channels(self, guild: discord.Guild) -> int:
        """
        Clean up stale voice channels that no longer exist on Discord.

        Args:
            guild: Discord guild to clean up

        Returns:
            Number of channels cleaned up
        """
        self._ensure_initialized()

        cleaned_count = 0

        # Get all voice channels for this guild from database
        voice_channels = await BaseRepository.fetch_all(
            """
            SELECT voice_channel_id, jtc_channel_id, owner_id
            FROM voice_channels
            WHERE guild_id = ? AND is_active = 1
            """,
            (guild.id,),
        )

        for voice_channel_id, _jtc_channel_id, _owner_id in voice_channels:
            # Check if channel still exists on Discord
            channel = guild.get_channel(voice_channel_id)
            if not channel:
                # Channel no longer exists, clean up database
                await self.cleanup_by_channel_id(voice_channel_id)
                cleaned_count += 1
                self.logger.debug(
                    f"Cleaned up stale voice channel record: {voice_channel_id}"
                )

        if cleaned_count > 0:
            self.logger.info(
                f"Cleaned up {cleaned_count} stale voice channels in {guild.name}"
            )

        return cleaned_count

    async def _is_on_cooldown(
        self, guild_id: int, jtc_channel_id: int, user_id: int, cooldown_seconds: int
    ) -> bool:
        """Check if a user is on cooldown for voice channel creation."""
        last_creation = await BaseRepository.fetch_value(
            """
            SELECT timestamp FROM voice_cooldowns
            WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
            """,
            (guild_id, jtc_channel_id, user_id),
        )

        if not last_creation:
            return False

        current_time = int(time.time())
        return (current_time - last_creation) < cooldown_seconds

    async def _update_cooldown(
        self, guild_id: int, jtc_channel_id: int, user_id: int
    ) -> None:
        """Update the cooldown timestamp for a user."""
        await BaseRepository.execute(
            """
            INSERT OR REPLACE INTO voice_cooldowns
            (guild_id, jtc_channel_id, user_id, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, jtc_channel_id, user_id, int(time.time())),
        )

    async def _store_voice_channel(
        self, guild_id: int, jtc_channel_id: int, owner_id: int, voice_channel_id: int
    ) -> None:
        """Store voice channel record in database."""
        await BaseRepository.execute(
            """
            INSERT OR REPLACE INTO voice_channels
            (guild_id, jtc_channel_id, owner_id, voice_channel_id)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, jtc_channel_id, owner_id, voice_channel_id),
        )

    async def cleanup_by_channel_id(self, voice_channel_id: int) -> None:
        """Clean up database records for a specific voice channel."""
        async with BaseRepository.transaction() as db:
            # Clean up settings for this specific channel
            await db.execute(
                """
                DELETE FROM voice_channel_settings
                WHERE voice_channel_id = ?
                """,
                (voice_channel_id,),
            )

            # Remove voice channel record entirely to avoid stale rows
            await db.execute(
                """
                DELETE FROM voice_channels
                WHERE voice_channel_id = ?
                """,
                (voice_channel_id,),
            )

    async def _purge_inactive_voice_channels(
        self, older_than_seconds: int | None = None
    ) -> int:
        """Delete inactive voice channel rows to keep the table lean."""
        query = "DELETE FROM voice_channels WHERE is_active = 0"
        params: tuple[int, ...] = ()
        if older_than_seconds is not None:
            cutoff = int(time.time()) - older_than_seconds
            query += " AND last_activity < ?"
            params = (cutoff,)

        return await BaseRepository.execute(query, params)

    async def _generate_channel_name(self, user: discord.Member) -> str:
        """Generate a name for a voice channel."""
        # Try to get game activity
        for activity in user.activities:
            if isinstance(activity, discord.Game):
                return f"{user.display_name}'s {activity.name}"

        # Fall back to default name
        return f"{user.display_name}'s Channel"

    async def _cleanup_task(self) -> None:
        """Background task to clean up expired data."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                # Clean up old cooldown records (older than 24 hours)
                cutoff_time = int(time.time()) - (24 * 3600)
                await BaseRepository.execute(
                    """
                    DELETE FROM voice_cooldowns
                    WHERE timestamp < ?
                    """,
                    (cutoff_time,),
                )

                self.logger.debug("Cleaned up old voice cooldown records")

                deleted_rows = await self._purge_inactive_voice_channels(
                    older_than_seconds=self.INACTIVE_CHANNEL_PURGE_DAYS * 24 * 3600
                )
                if deleted_rows:
                    self.logger.debug(
                        f"Purged {deleted_rows} inactive voice channel records"
                    )

                await self._cleanup_stale_locks()

            except asyncio.CancelledError:
                self.logger.debug("Cleanup task cancelled, exiting gracefully")
                break
            except Exception as e:
                self.logger.exception("Error in voice cleanup task", exc_info=e)

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the voice service."""
        base_health = await super().health_check()

        try:
            # Count active voice channels
            active_channels = await BaseRepository.fetch_value(
                "SELECT COUNT(*) FROM voice_channels WHERE is_active = 1",
            )
            active_channels = active_channels or 0

            # Count total cooldown records
            cooldown_records = await BaseRepository.fetch_value(
                "SELECT COUNT(*) FROM voice_cooldowns",
            )
            cooldown_records = cooldown_records or 0
        except Exception:
            active_channels = "error"
            cooldown_records = "error"

        return {
            **base_health,
            "active_voice_channels": active_channels,
            "cooldown_records": cooldown_records,
            "creation_locks": len(self._creation_locks),
        }

