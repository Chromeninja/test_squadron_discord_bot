"""
VoiceSetupMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
from typing import Any

import discord  # type: ignore[import-not-found]

from helpers.task_queue import enqueue_task
from services.db.database import Database
from services.db.repository import BaseRepository
from services.voice_channel_helpers import (
    validate_jtc_permissions,
)
from utils.types import VoiceChannelResult
from services.voice_base_mixin import VoiceServiceBase


class VoiceSetupMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def _validate_jtc_permissions(
        self, category: discord.CategoryChannel
    ) -> tuple[bool, str | None]:
        """Validate bot has permissions to create channels in a category."""
        return validate_jtc_permissions(
            category,
            bot=self.bot,
            logger=self.logger,
        )

    async def voice_setup_guard(
        self,
        category: discord.CategoryChannel,
        member: discord.Member,
    ) -> tuple[bool, str | None]:
        """
        Comprehensive pre-check before voice channel creation.

        Validates:
        - Bot permissions in category (Manage Channels)
        - Bot permissions in guild (Move Members)
        - Bot role hierarchy vs target member (for overwrites)

        Args:
            category: Category to create channel in
            member: Member to create channel for

        Returns:
            Tuple of (can_proceed, error_message)

        Observability:
            - Logs INFO on guard check start
            - Logs WARNING on any check failure
            - Logs DEBUG on successful guard pass
        """
        self.logger.info(
            f"Voice setup guard check for member {member.id} in category {category.id if category else 'None'}"
        )

        # Check base permissions
        can_create, error = await self._validate_jtc_permissions(category)
        if not can_create:
            return False, error

        # Check role hierarchy for permission overwrites
        if self.bot and self.bot.user:
            bot_member = category.guild.get_member(self.bot.user.id)
            if bot_member:
                try:
                    if bot_member.top_role <= member.top_role:
                        self.logger.warning(
                            f"Bot role '{bot_member.top_role.name}' not higher than "
                            f"member role '{member.top_role.name}'; permission overwrites may fail",
                            extra={
                                "guild_id": category.guild.id,
                                "member_id": member.id,
                                "bot_role_position": bot_member.top_role.position,
                                "member_role_position": member.top_role.position,
                            },
                        )
                        # This is a warning, not a failure - channel creation can proceed
                        # but overwrites may not work
                except (TypeError, AttributeError):
                    # Mock objects may not have proper role comparison
                    pass

        self.logger.debug(
            f"Voice setup guard passed for member {member.id}",
            extra={"guild_id": category.guild.id, "category_id": category.id},
        )
        return True, None

    async def _create_voice_channel_queued(
        self,
        category: discord.CategoryChannel,
        *,
        name: str,
        reason: str,
        **kwargs: Any,
    ) -> discord.VoiceChannel | None:
        """Create a voice channel via the task queue to respect rate limits."""

        async def _task() -> discord.VoiceChannel:
            return await category.create_voice_channel(
                name=name, reason=reason, **kwargs
            )

        try:
            # enqueue_task is annotated to return None but actually returns a Future
            future = await enqueue_task(_task)  # type: ignore[func-returns-value]
            if isinstance(future, asyncio.Future):
                return await asyncio.shield(future)
            return None
        except Exception as e:
            self.logger.exception("Error queueing voice channel creation", exc_info=e)
            return None

    async def create_jtc_channel(
        self, guild_id: int, category: discord.CategoryChannel, channel_name: str
    ) -> tuple[discord.VoiceChannel | None, str | None]:
        """
        Create a single JTC channel in a category.

        Shared method used by both setup and add commands.

        Args:
            guild_id: Discord guild ID
            category: Category to create channel in
            channel_name: Name for the new channel

        Returns:
            Tuple of (created_channel, error_message). If successful, error_message is None.
        """
        try:
            # Validate permissions first
            can_create, error = await self._validate_jtc_permissions(category)
            if not can_create:
                return None, error

            # Create the channel via task queue to respect rate limits
            jtc_channel = await self._create_voice_channel_queued(
                category,
                name=channel_name,
                reason="JTC channel creation via admin command",
            )

            if jtc_channel is None:
                return None, "Failed to create JTC channel via task queue"

            self.logger.info(
                f"Created JTC channel {jtc_channel.id} ({channel_name}) in guild {guild_id}"
            )

            return jtc_channel, None

        except discord.Forbidden as e:
            error_msg = f"Permission denied creating JTC channel: {e}"
            self.logger.exception(error_msg)
            return None, error_msg
        except discord.HTTPException as e:
            error_msg = f"Discord API error creating JTC channel: {e}"
            self.logger.exception(error_msg)
            return None, error_msg
        except Exception as e:
            self.logger.exception("Error creating JTC channel", exc_info=e)
            return None, str(e)

    async def add_jtc_channel_to_config(
        self, guild_id: int, channel_id: int
    ) -> tuple[bool, str | None]:
        """
        Add a JTC channel to guild configuration.

        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to add

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check for duplicates
            existing_jtc = await self.config_service.get_guild_jtc_channels(guild_id)
            if channel_id in existing_jtc:
                return False, f"Channel {channel_id} is already configured as JTC"

            # Add to config
            await self.config_service.add_guild_jtc_channel(guild_id, channel_id)

            self.logger.info(
                f"Added JTC channel {channel_id} to guild {guild_id} config"
            )
            return True, None

        except Exception as e:
            self.logger.exception("Error adding JTC channel to config", exc_info=e)
            return False, str(e)

    async def remove_jtc_channel_from_config(
        self, guild_id: int, channel_id: int, cleanup_managed: bool = True
    ) -> dict[str, Any]:
        """
        Remove a JTC channel from guild configuration and clean up associated data.

        Args:
            guild_id: Discord guild ID
            channel_id: Voice channel ID to remove
            cleanup_managed: Whether to cleanup managed channels belonging to this JTC

        Returns:
            Dict with results:
            - success: bool
            - error: str | None
            - managed_cleanup: dict from cleanup_stale_jtc_managed_channels
            - db_purge: dict from Database.purge_stale_jtc_data
        """
        result = {
            "success": False,
            "error": None,
            "managed_cleanup": {},
            "db_purge": {},
        }

        try:
            # Check if channel is configured
            existing_jtc = await self.config_service.get_guild_jtc_channels(guild_id)
            if channel_id not in existing_jtc:
                result["error"] = f"Channel {channel_id} is not configured as JTC"
                return result

            # Remove from config
            await self.config_service.remove_guild_jtc_channel(guild_id, channel_id)
            self.logger.info(
                f"Removed JTC channel {channel_id} from guild {guild_id} config"
            )

            # Clean up managed channels if requested
            if cleanup_managed:
                result[
                    "managed_cleanup"
                ] = await self.cleanup_stale_jtc_managed_channels(
                    guild_id, {channel_id}
                )

            # Purge database records
            from services.db.database import Database

            result["db_purge"] = await Database.purge_stale_jtc_data(
                guild_id, {channel_id}
            )

            self.logger.info(
                f"JTC channel {channel_id} removal complete for guild {guild_id}: "
                f"managed_cleanup={result['managed_cleanup']}, db_purge={result['db_purge']}"
            )

            result["success"] = True
            return result

        except Exception as e:
            self.logger.exception("Error removing JTC channel from config", exc_info=e)
            result["error"] = str(e)
            return result

    async def setup_voice_system(
        self, guild_id: int, category: discord.CategoryChannel, num_channels: int = 1
    ) -> VoiceChannelResult:
        """
        Set up the voice channel system for a guild with stale JTC data cleanup.

        Args:
            guild_id: Discord guild ID
            category: Category to create channels in
            num_channels: Number of JTC channels to create

        Returns:
            VoiceChannelResult with success status
        """
        try:
            from services.db.database import Database

            # Validate permissions once before creating channels
            can_create, error = await self._validate_jtc_permissions(category)
            if not can_create:
                return VoiceChannelResult(
                    False, error=error or "JTC permission check failed"
                )

            # Step 1: Get old JTC channels before making changes
            old_jtc_channels = await self.config_service.get_guild_jtc_channels(
                guild_id
            )
            self.logger.info(
                f"Current JTC channels for guild {guild_id}: {old_jtc_channels}"
            )

            # Step 2: Create new JTC channels
            created_channels = []
            for i in range(num_channels):
                channel_name = (
                    f"Join to Create {i + 1}" if num_channels > 1 else "Join to Create"
                )

                # Create the voice channel via task queue (inherit permissions from parent category)
                jtc_channel = await self._create_voice_channel_queued(
                    category,
                    name=channel_name,
                    reason="Voice system setup",
                )

                if jtc_channel is None:
                    return VoiceChannelResult(
                        False, error="JTC channel creation failed"
                    )

                created_channels.append(jtc_channel.id)
                self.logger.info(
                    f"Created JTC channel {jtc_channel.id} ({channel_name})"
                )

            # Step 3: Compute stale JTC IDs (old ones not in new ones)
            new_jtc_set = set(created_channels)
            old_jtc_set = set(old_jtc_channels) if old_jtc_channels else set()
            stale_jtc_ids = old_jtc_set - new_jtc_set

            self.logger.info(f"New JTC channels: {new_jtc_set}")
            self.logger.info(f"Stale JTC channels to clean up: {stale_jtc_ids}")

            # Step 4: Purge stale JTC data if any
            purge_stats = {}
            cleanup_stats = {}
            if stale_jtc_ids:
                # Clean up managed channels first (before database purge)
                cleanup_stats = await self.cleanup_stale_jtc_managed_channels(
                    guild_id, stale_jtc_ids
                )

                # Purge database records
                purge_stats = await Database.purge_stale_jtc_data(
                    guild_id, stale_jtc_ids
                )

                self.logger.info(
                    "Stale JTC cleanup completed - Purged: %s, Channels: %s",
                    purge_stats,
                    cleanup_stats,
                )

            # Step 5: Update guild configuration with new JTC channels
            # Replace all JTC channels with the new ones
            await self.config_service.set_guild_setting(
                guild_id, "voice.jtc_channels", created_channels
            )

            # Save voice category
            await self.config_service.set_guild_setting(
                guild_id, "voice_category_id", category.id
            )

            # Step 6: Log summary
            total_purged_rows = sum(purge_stats.values()) if purge_stats else 0
            deleted_channels_count = (
                len(cleanup_stats.get("deleted_channels", [])) if cleanup_stats else 0
            )
            failed_channels_count = (
                len(cleanup_stats.get("failed_channels", [])) if cleanup_stats else 0
            )

            self.logger.info(
                "Voice system setup complete for guild %s: Created %d JTC channels, Removed %d stale JTC IDs, "
                "Purged %d database rows, Deleted %d empty channels, Failed to delete %d channels",
                guild_id,
                len(created_channels),
                len(stale_jtc_ids),
                total_purged_rows,
                deleted_channels_count,
                failed_channels_count,
            )

            return VoiceChannelResult(success=True)

        except Exception as e:
            self.logger.exception("Error setting up voice system", exc_info=e)
            return VoiceChannelResult(success=False, error="UNKNOWN")

    async def delete_user_owned_channel(
        self, guild_id: int, user_id: int
    ) -> dict[str, Any]:
        """
        Delete user's owned voice channel and remove it from cache.

        Args:
            guild_id: Discord guild ID
            user_id: User ID whose channel to delete

        Returns:
            Dict with success status and deleted channel info
        """
        result = {
            "success": False,
            "channel_deleted": False,
            "channel_id": None,
            "error": None,
        }

        try:
            # Find the user's active voice channel
            channel_info = await self.get_user_voice_channel_info(guild_id, user_id)

            if not channel_info:
                result["success"] = True  # No channel to delete is considered success
                return result

            channel_id = channel_info.channel_id
            result["channel_id"] = channel_id

            # Try to get the actual Discord channel and delete it
            if self.bot:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    deleted = await self._delete_channel_safe(
                        channel,
                        reason=f"Admin reset for user {user_id}",
                        cleanup_tracking=False,  # We handle tracking below
                    )
                    result["channel_deleted"] = deleted
                else:
                    self.logger.warning(f"Channel {channel_id} not found in bot cache")

            # Remove from managed channels cache
            self.managed_voice_channels.discard(channel_id)

            result["success"] = True

        except Exception as e:
            self.logger.exception("Error deleting user owned channel", exc_info=e)
            result["error"] = str(e)

        return result

    async def get_all_guild_managed_channels(self, guild_id: int) -> list[int]:
        """
        Get all managed voice channels for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of voice channel IDs
        """
        try:
            rows = await BaseRepository.fetch_all(
                "SELECT voice_channel_id FROM voice_channels WHERE guild_id = ? AND is_active = 1",
                (guild_id,),
            )
            return [row[0] for row in rows]

        except Exception as e:
            self.logger.exception("Error getting guild managed channels", exc_info=e)
            return []

    async def purge_voice_data_with_cache_clear(
        self, guild_id: int, user_id: int | None = None
    ) -> dict[str, int]:
        """
        Purge voice data from database and clear relevant caches.

        Args:
            guild_id: Discord guild ID
            user_id: If provided, purge only this user's data. If None, purge all users in guild.

        Returns:
            Dict mapping table names to number of rows deleted.
        """
        # Get managed channels before purging if doing guild-wide clear
        if user_id is None:
            managed_channels = await self.get_all_guild_managed_channels(guild_id)
        else:
            # For single user, get their channel info
            managed_channels = []
            channel_info = await self.get_user_voice_channel_info(guild_id, user_id)
            if channel_info:
                managed_channels = [channel_info.channel_id]

        # Purge database records
        deleted_counts = await Database.purge_voice_data(guild_id, user_id)

        # Clear cache entries for affected channels
        for channel_id in managed_channels:
            self.managed_voice_channels.discard(channel_id)

        self.logger.info(
            f"Purged voice data and cleared cache for guild {guild_id}, user {user_id}: "
            f"database={deleted_counts}, cache_cleared={len(managed_channels)} channels"
        )

        return deleted_counts

    async def cleanup_stale_jtc_managed_channels(
        self, guild_id: int, stale_jtc_ids: set[int]
    ) -> dict[str, Any]:
        """
        Find and safely delete empty managed channels belonging to stale JTC channels.

        Args:
            guild_id: Discord guild ID
            stale_jtc_ids: Set of stale JTC channel IDs

        Returns:
            Dict with cleanup statistics and any errors
        """
        if not stale_jtc_ids:
            return {"deleted_channels": [], "failed_channels": [], "errors": []}

        deleted_channels = []
        failed_channels = []
        errors = []

        try:
            # Find managed channels that belong to stale JTC IDs
            stale_jtc_list = [int(x) for x in stale_jtc_ids]  # defensive cast

            # Short-circuit if no stale JTC channels to avoid IN () syntax
            if not stale_jtc_list:
                return {"deleted_channels": [], "failed_channels": [], "errors": []}

            # Build parameterized query to avoid SQL injection
            placeholders = ",".join("?" * len(stale_jtc_list))
            query = f"""
                SELECT voice_channel_id, jtc_channel_id
                FROM voice_channels
                WHERE guild_id = ? AND jtc_channel_id IN ({placeholders}) AND is_active = 1
            """

            stale_managed_channels = await BaseRepository.fetch_all(
                query,
                (guild_id, *stale_jtc_list),
            )

            # Attempt to delete each managed channel if it's empty
            if self.bot:
                for voice_channel_id, jtc_channel_id in stale_managed_channels:
                    try:
                        channel = self.bot.get_channel(voice_channel_id)
                        if channel and isinstance(channel, discord.VoiceChannel):
                            # Only delete if channel is empty or has only bot members
                            non_bot_members = [
                                m
                                for m in channel.members
                                if isinstance(m, discord.Member) and not m.bot
                            ]
                            if len(non_bot_members) == 0:
                                deleted = await self._delete_channel_safe(
                                    channel,
                                    reason=f"Cleanup stale JTC {jtc_channel_id} managed channel",
                                )
                                if deleted:
                                    deleted_channels.append(
                                        {
                                            "voice_channel_id": voice_channel_id,
                                            "jtc_channel_id": jtc_channel_id,
                                        }
                                    )
                            else:
                                # Channel has users, don't delete but log
                                self.logger.warning(
                                    f"Skipping deletion of managed channel {voice_channel_id} - has {len(non_bot_members)} non-bot members"
                                )
                                failed_channels.append(
                                    {
                                        "voice_channel_id": voice_channel_id,
                                        "jtc_channel_id": jtc_channel_id,
                                        "reason": "has_users",
                                    }
                                )
                        elif channel:
                            # Channel exists but we can't check members (shouldn't happen for voice channels)
                            self.logger.warning(
                                f"Cannot check member count for channel {voice_channel_id}, skipping deletion"
                            )
                            failed_channels.append(
                                {
                                    "voice_channel_id": voice_channel_id,
                                    "jtc_channel_id": jtc_channel_id,
                                    "reason": "cannot_check_members",
                                }
                            )
                        else:
                            # Channel doesn't exist in bot cache, remove from our tracking anyway
                            self.managed_voice_channels.discard(voice_channel_id)
                            self.logger.debug(
                                f"Managed channel {voice_channel_id} not found, removed from cache"
                            )

                    except Exception as e:
                        error_msg = (
                            f"Error deleting managed channel {voice_channel_id}: {e}"
                        )
                        self.logger.exception(error_msg)
                        errors.append(error_msg)
                        failed_channels.append(
                            {
                                "voice_channel_id": voice_channel_id,
                                "jtc_channel_id": jtc_channel_id,
                                "reason": "exception",
                                "error": str(e),
                            }
                        )

        except Exception as e:
            error_msg = f"Error during stale JTC cleanup: {e}"
            self.logger.exception(error_msg)
            errors.append(error_msg)

        result = {
            "deleted_channels": deleted_channels,
            "failed_channels": failed_channels,
            "errors": errors,
        }

        self.logger.info(
            f"Stale JTC cleanup for guild {guild_id}: "
            f"deleted={len(deleted_channels)}, failed={len(failed_channels)}, errors={len(errors)}"
        )

        return result

    async def create_admin_settings_embed(
        self,
        guild_id: int,
        user_id: int,
        user: discord.Member,
        settings: dict[str, Any],
    ) -> discord.Embed:
        """
        Create an admin view of a user's voice channel settings.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            user: Discord member object
            settings: Settings dictionary

        Returns:
            Discord embed with formatted admin view
        """
        embed = discord.Embed(
            title=f"🔧 Voice Settings for {user.display_name}",
            description=f"Administrative view of voice channel settings for {user.mention}",
            color=discord.Color.orange(),
        )

        if not settings:
            embed.add_field(
                name="Settings", value="No custom settings found.", inline=False
            )
        else:
            settings_text = []
            for key, value in settings.items():
                formatted_key = key.replace("_", " ").title()
                settings_text.append(f"**{formatted_key}:** {value}")

            embed.add_field(
                name="Current Settings", value="\n".join(settings_text), inline=False
            )

        # Add user info
        embed.add_field(
            name="User Info",
            value=f"**ID:** {user_id}\n**Mention:** {user.mention}",
            inline=True,
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        return embed
