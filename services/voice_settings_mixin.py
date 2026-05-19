"""
VoiceSettingsMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord  # type: ignore[import-not-found]

from helpers.embeds import EmbedColors
from helpers.voice_settings import get_voice_settings_snapshots
from services.db.repository import BaseRepository
from services.voice_base_mixin import VoiceServiceBase
from utils.types import VoiceChannelInfo, VoiceChannelResult

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot


class VoiceSettingsMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def get_jtc_for_owned_channel(
        self, voice_channel_id: int, owner_id: int
    ) -> int | None:
        """Return the JTC channel ID for a managed channel owned by the given user.

        Args:
            voice_channel_id: The voice channel to look up.
            owner_id: Expected owner Discord user ID.

        Returns:
            The JTC channel ID if the channel is active and owned by the user,
            otherwise ``None``.
        """
        return await BaseRepository.fetch_value(
            "SELECT jtc_channel_id FROM voice_channels "
            "WHERE voice_channel_id = ? AND owner_id = ? AND is_active = 1",
            (voice_channel_id, owner_id),
        )

    async def get_voice_settings_snapshot(
        self,
        guild_id: int,
        jtc_channel_id: int,
        owner_id: int,
        voice_channel_id: int | None = None,
        guild: discord.Guild | None = None,
    ) -> VoiceSettingsSnapshot | None:
        """
        Get a complete snapshot of voice channel settings.

        This is the unified method for retrieving voice settings used by:
        - Discord commands (/voice list, /voice admin_list)
        - Backend API endpoints (/api/voice/search, /api/voice/active, /api/voice/user-settings)

        Args:
            guild_id: Discord guild ID
            jtc_channel_id: Join-to-create channel ID
            owner_id: Channel owner user ID
            voice_channel_id: Optional voice channel ID if currently active
            guild: Optional Discord guild object for name resolution

        Returns:
            VoiceSettingsSnapshot or None if no settings found
        """
        from utils.types import (
            PermissionOverride,
            PrioritySpeakerSetting,
            PTTSetting,
            SoundboardSetting,
            VoiceSettingsSnapshot,
        )

        try:
            async with BaseRepository.transaction() as db:
                # Get basic channel settings
                cursor = await db.execute(
                    """
                    SELECT channel_name, user_limit, lock
                    FROM channel_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                    """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                row = await cursor.fetchone()

                if not row:
                    # No settings found
                    return None

                channel_name, user_limit, lock = row

                # Get channel metadata if voice_channel_id provided
                created_at = None
                last_activity = None
                is_active = False

                if voice_channel_id:
                    cursor = await db.execute(
                        """
                        SELECT created_at, last_activity, is_active
                        FROM voice_channels
                        WHERE voice_channel_id = ? AND owner_id = ?
                    """,
                        (voice_channel_id, owner_id),
                    )
                    vc_row = await cursor.fetchone()
                    if vc_row:
                        created_at, last_activity, is_active = vc_row
                        is_active = bool(is_active)

                # Get permissions
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, permission
                    FROM channel_permissions
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                perm_rows = await cursor.fetchall()

                # Get PTT settings
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, ptt_enabled
                    FROM channel_ptt_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                ptt_rows = await cursor.fetchall()

                # Get priority speaker settings
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, priority_enabled
                    FROM channel_priority_speaker_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                priority_rows = await cursor.fetchall()

                # Get soundboard settings
                cursor = await db.execute(
                    """
                    SELECT target_id, target_type, soundboard_enabled
                    FROM channel_soundboard_settings
                    WHERE guild_id = ? AND jtc_channel_id = ? AND user_id = ?
                """,
                    (guild_id, jtc_channel_id, owner_id),
                )
                soundboard_rows = await cursor.fetchall()

                # Build snapshot with unresolved names (resolution happens separately)
                permissions = [
                    PermissionOverride(
                        target_id=str(target_id),
                        target_type=target_type,
                        permission=permission,
                    )
                    for target_id, target_type, permission in perm_rows
                ]

                ptt_settings = [
                    PTTSetting(
                        target_id=str(target_id),
                        target_type=target_type,
                        ptt_enabled=bool(ptt_enabled),
                    )
                    for target_id, target_type, ptt_enabled in ptt_rows
                ]

                priority_settings = [
                    PrioritySpeakerSetting(
                        target_id=str(target_id),
                        target_type=target_type,
                        priority_enabled=bool(priority_enabled),
                    )
                    for target_id, target_type, priority_enabled in priority_rows
                ]

                soundboard_settings = [
                    SoundboardSetting(
                        target_id=str(target_id),
                        target_type=target_type,
                        soundboard_enabled=bool(soundboard_enabled),
                    )
                    for target_id, target_type, soundboard_enabled in soundboard_rows
                ]

                snapshot = VoiceSettingsSnapshot(
                    guild_id,
                    jtc_channel_id,
                    owner_id,
                    voice_channel_id,
                    channel_name,
                    user_limit,
                    bool(lock),
                    created_at,
                    last_activity,
                    is_active,
                    permissions,
                    ptt_settings,
                    priority_settings,
                    soundboard_settings,
                )

                # Resolve names if guild provided
                if guild:
                    from helpers.voice_settings import resolve_target_names

                    await resolve_target_names(guild, snapshot)

                return snapshot

        except Exception as e:
            self.logger.exception("Error getting voice settings snapshot", exc_info=e)
            return None

    async def get_user_settings_snapshots(
        self, guild_id: int, user_id: int
    ) -> list[VoiceSettingsSnapshot]:
        """Return snapshots for all JTCs a user has settings in using shared helper logic."""

        self._ensure_initialized()
        return await get_voice_settings_snapshots(guild_id, user_id)

    # Additional methods for cog integration

    async def create_user_voice_channel(
        self, guild_id: int, user_id: int, user: discord.Member
    ) -> VoiceChannelResult:
        """
        Create a voice channel for a user with result handling.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            user: Discord member object

        Returns:
            VoiceChannelResult with success status and error code (not formatted message)
        """
        try:
            guild = user.guild
            if not guild:
                return VoiceChannelResult(False, error="UNKNOWN")

            # Find a suitable JTC channel (simplified for now)
            jtc_channels = await self._get_guild_jtc_channels(guild_id)
            if not jtc_channels:
                return VoiceChannelResult(False, error="NO_JTC_CONFIGURED")

            # Use first available JTC channel
            jtc_channel_id = jtc_channels[0]
            jtc_channel = guild.get_channel(jtc_channel_id)

            if not jtc_channel or not isinstance(jtc_channel, discord.VoiceChannel):
                return VoiceChannelResult(False, error="JTC_NOT_FOUND")

            # Check if user can create
            can_create, reason = await self.can_create_voice_channel(
                guild_id, jtc_channel_id, user_id
            )

            if not can_create:
                return VoiceChannelResult(False, error=reason)

            # Serialize creation per user to avoid duplicate channels from concurrent calls
            lock = await self._get_creation_lock(guild.id, user.id)
            creation_marked = False
            channel: discord.VoiceChannel | None = None

            async with lock:
                if self._is_user_creating(guild.id, user.id):
                    return VoiceChannelResult(False, error="CREATING")

                self._mark_user_creating(guild.id, user.id)
                creation_marked = True
                try:
                    channel = await self._create_user_channel(guild, jtc_channel, user)
                finally:
                    if creation_marked:
                        self._spawn_background_task(
                            self._delayed_unmark_user_creating(
                                guild.id,
                                user.id,
                                delay=self._creation_unmark_delay,
                            ),
                            name=f"voice.unmark_user.{guild.id}.{user.id}",
                        )

            if channel:
                return VoiceChannelResult(
                    True, channel_id=channel.id, channel_mention=channel.mention
                )

            return VoiceChannelResult(False, error="CREATION_FAILED")

        except Exception as e:
            self.logger.exception("Error creating user voice channel", exc_info=e)
            return VoiceChannelResult(False, error="UNKNOWN")

    async def get_user_voice_channel_info(
        self, guild_id: int, user_id: int
    ) -> VoiceChannelInfo | None:
        """
        Get a user's active voice channel info.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            VoiceChannelInfo if found, None otherwise
        """
        try:
            row = await BaseRepository.fetch_one(
                """
                SELECT guild_id, jtc_channel_id, voice_channel_id, owner_id,
                       created_at, last_activity, is_active
                FROM voice_channels
                WHERE guild_id = ? AND owner_id = ? AND is_active = 1
                LIMIT 1
                """,
                (guild_id, user_id),
            )

            if row:
                return VoiceChannelInfo(
                    guild_id=row[0],
                    jtc_channel_id=row[1],
                    channel_id=row[2],
                    owner_id=row[3],
                    created_at=row[4],
                    last_activity=row[5],
                    is_active=bool(row[6]),
                )
            return None

        except Exception as e:
            self.logger.exception("Error getting user voice channel", exc_info=e)
            return None

    async def create_settings_embed(self, guild_id: int, user_id: int) -> discord.Embed:
        """
        Create an embed showing voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Discord embed with settings information
        """
        embed = discord.Embed(
            title="🔧 Voice Channel Settings",
            description="Manage your voice channel settings below.",
            color=EmbedColors.BLURPLE,
        )

        # Add current settings (placeholder implementation)
        embed.add_field(
            name="Current Settings", value="Settings would be loaded here", inline=False
        )

        return embed

    async def create_settings_view(
        self, guild_id: int, user_id: int
    ) -> discord.ui.View:
        """
        Create a view for voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID

        Returns:
            Discord UI view with settings controls
        """
        # This would return an actual settings view
        # For now, return a basic view
        return discord.ui.View()

    async def get_admin_role_ids(self, guild_id: int) -> list[int]:
        """Get privileged role IDs (admins + moderators) for a specific guild.

        Args:
            guild_id: The Discord guild ID to get admin roles for

        Returns:
            List of role IDs that have admin or moderator permissions
        """
        try:
            bot = getattr(self, "bot", None)
            if not bot:
                return []

            from helpers.permissions_helper import get_configured_privileged_role_ids

            return await get_configured_privileged_role_ids(bot, guild_id)
        except Exception as e:
            self.logger.exception(
                f"Error getting admin role IDs for guild {guild_id}", exc_info=e
            )
            return []

    def get_voice_channel_members(self, channel_id: int) -> list[int]:
        """
        Get list of user IDs currently in a voice channel.

        This data comes from the Gateway cache (no Discord API calls).
        Returns empty list if channel has no members or is not cached.

        Args:
            channel_id: Discord voice channel ID

        Returns:
            List of user IDs currently in the channel
        """
        return list(self._voice_channel_members.get(channel_id, set()))

