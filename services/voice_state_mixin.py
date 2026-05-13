"""
VoiceStateMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
from inspect import isawaitable

import discord  # type: ignore[import-not-found]

from services.db.repository import BaseRepository
from services.voice_base_mixin import VoiceServiceBase


class VoiceStateMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def handle_voice_state_change(
        self,
        member: discord.Member,
        before_channel: discord.VoiceChannel | None,
        after_channel: discord.VoiceChannel | None,
    ) -> None:
        """
        Handle voice state changes for join-to-create functionality.

        Args:
            member: Discord member
            before_channel: Channel member left (if any)
            after_channel: Channel member joined (if any)
        """
        guild = member.guild
        guild_id = guild.id

        if self.debug_logging_enabled:
            self.logger.info(
                "VS: event guild=%s member=%s before_channel=%s after_channel=%s",
                guild_id,
                getattr(member, "id", None),
                before_channel.id if before_channel else None,
                after_channel.id if after_channel else None,
            )

        # Skip cache updates when the user stayed in the same channel
        # (mute/deafen/stream toggles still fire voice_state_update)
        same_channel = (
            before_channel is not None
            and after_channel is not None
            and before_channel.id == after_channel.id
        )

        # Fast-path: mute/deafen/stream toggles don't change channels,
        # so there is nothing to do — avoid DB queries entirely.
        if same_channel:
            return

        # Update voice channel members cache
        if before_channel:
            # Remove user from previous channel
            if before_channel.id in self._voice_channel_members:
                self._voice_channel_members[before_channel.id].discard(member.id)
                # Clean up empty sets
                if not self._voice_channel_members[before_channel.id]:
                    del self._voice_channel_members[before_channel.id]

        if after_channel:
            # Add user to new channel
            if after_channel.id not in self._voice_channel_members:
                self._voice_channel_members[after_channel.id] = set()
            self._voice_channel_members[after_channel.id].add(member.id)

        # Handle leaving a managed channel - clean up if empty
        left_managed = False
        if before_channel:
            left_managed = await self._is_managed_channel(before_channel.id)
            if left_managed:
                await self._handle_channel_left(before_channel, member)

        # Handle joining a join-to-create channel
        # Treat any move into a JTC (including from another JTC) as a join-to-create
        is_jtc_after = False
        if after_channel:
            is_jtc_after = await self._is_join_to_create_channel(
                guild_id, after_channel.id
            )

        is_true_join = after_channel is not None and is_jtc_after

        # If the user came from a managed channel, allow bypassing cooldown so they can hop back to JTC immediately.
        bypass_cooldown = left_managed

        if self.debug_logging_enabled:
            self.logger.info(
                "VS: classification guild=%s member=%s is_true_join=%s is_jtc_after=%s before_channel=%s",
                guild_id,
                getattr(member, "id", None),
                is_true_join,
                is_jtc_after,
                before_channel.name if before_channel else None,
            )

        if is_true_join and after_channel is not None:
            if self._is_user_creating(guild_id, member.id):
                if self.debug_logging_enabled:
                    self.logger.debug(
                        f"Skipping voice state update for {member.display_name} - creation in progress"
                    )
                return
            await self._handle_join_to_create(
                guild, after_channel, member, bypass_cooldown=bypass_cooldown
            )

    async def _is_managed_channel(self, channel_id: int) -> bool:
        """Check if a channel is managed by the bot."""
        try:
            is_managed = await BaseRepository.exists(
                "SELECT 1 FROM voice_channels WHERE voice_channel_id = ? AND is_active = 1 LIMIT 1",
                (channel_id,),
            )
            if self.debug_logging_enabled:
                self.logger.debug(
                    "Channel %s is %smanaged",
                    channel_id,
                    "" if is_managed else "not ",
                )
            return is_managed
        except Exception as e:
            self.logger.exception("Error checking if channel is managed", exc_info=e)
            return False

    async def _is_join_to_create_channel(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is a join-to-create channel."""
        try:
            guild_id_int = int(guild_id)
            channel_id_int = int(channel_id)
            jtc_channels = await self.config_service.get_guild_jtc_channels(
                guild_id_int
            )
            return channel_id_int in jtc_channels
        except Exception as e:
            self.logger.exception("Error checking if channel is JTC", exc_info=e)
            return False

    async def _handle_channel_left(
        self, channel: discord.VoiceChannel, member: discord.Member
    ) -> None:
        """Handle cleanup when a member leaves a managed channel."""
        try:
            self.logger.info(
                f"Member {member.display_name} left managed channel {channel.name} (ID: {channel.id})"
            )
            # Use the live gateway member list as the authoritative count
            # (our _voice_channel_members cache is updated *before* this call)
            member_count = self._get_member_count(channel)
            # Check if channel is now empty
            if member_count == 0:
                # Yield to the event loop so any pending voice-state
                # updates (e.g. a user joining right now) can be processed
                # before we commit to deletion.
                await asyncio.sleep(0)
                fresh_count = self._get_member_count(channel)
                if fresh_count > 0:
                    self.logger.info(
                        "Channel %s appeared empty but now has %d member(s) — skipping cleanup",
                        channel.name,
                        fresh_count,
                    )
                    return
                self.logger.info(
                    f"Channel {channel.name} (ID: {channel.id}) is now empty, performing immediate cleanup"
                )
                await self._cleanup_empty_channel(channel)
            elif self.debug_logging_enabled:
                self.logger.debug(
                    "Channel %s still has %d members, no cleanup needed",
                    channel.name,
                    member_count,
                )
        except Exception as e:
            self.logger.exception("Error handling channel left", exc_info=e)

    async def _notify_bot_spam_channel(
        self, guild: discord.Guild, message: str
    ) -> None:
        """Send a notification to the bot spam channel if configured."""
        try:
            bot_spam_channel_id = await self.config_service.get_guild_setting(
                guild.id, "channels.bot_spam_channel_id"
            )
            if bot_spam_channel_id:
                bot_spam_channel = guild.get_channel(bot_spam_channel_id)
                if bot_spam_channel and isinstance(
                    bot_spam_channel, discord.TextChannel
                ):
                    await bot_spam_channel.send(message)
                    if self.debug_logging_enabled:
                        self.logger.debug(
                            "Sent notification to bot spam channel: %s", message
                        )
        except Exception as e:
            self.logger.warning(f"Failed to send bot spam channel notification: {e}")

    async def _send_settings_message_to_vc(
        self,
        voice_channel: discord.VoiceChannel,
        member: discord.Member,
        view: discord.ui.View,
    ) -> None:
        """Send the settings message to the voice channel via its send() method."""

        if self.debug_logging_enabled:
            self.logger.debug(
                "Sending settings message to VC %s for member %s",
                voice_channel.id,
                member.id,
            )

        try:
            send_fn = getattr(voice_channel, "send", None)
            if not callable(send_fn):
                self.logger.warning(
                    "Voice channel %s does not support send(); skipping settings message",
                    getattr(voice_channel, "id", "unknown"),
                )
                return

            send_result = send_fn(
                f"{member.mention}, configure your channel settings:",
                view=view,
            )
            if isawaitable(send_result):
                await send_result

            if self.debug_logging_enabled:
                self.logger.debug(
                    "Successfully sent settings message to VC %s",
                    voice_channel.id,
                )
        except discord.Forbidden:
            self.logger.warning(
                f"Missing permissions to send settings message in VC {voice_channel.id}"
            )
        except discord.HTTPException as e:
            self.logger.warning(
                f"HTTP error sending settings message to VC {voice_channel.id}: {e}"
            )
        except Exception as e:
            self.logger.exception(
                f"Error sending VC settings message to {voice_channel.id}: {e}"
            )

    async def _cleanup_empty_channel(
        self, channel_or_id: discord.VoiceChannel | int
    ) -> None:
        """Immediately cleanup an empty managed channel."""
        # Determine channel_id and channel object
        channel = None
        channel_id = None

        if isinstance(channel_or_id, int):
            channel_id = channel_or_id
            channel = self.bot.get_channel(channel_id) if self.bot else None
        else:
            channel = channel_or_id
            channel_id = getattr(channel_or_id, "id", None)

        if channel_id is None:
            self.logger.warning(
                "Cleanup requested for channel without id (type=%s); skipping deletion",
                type(channel_or_id).__name__,
            )
            return

        # If channel is None (already deleted), just clean up DB and cache
        if channel is None:
            self.logger.info(
                f"Channel {channel_id} already deleted, cleaning up DB and cache"
            )
            # Remove from managed channels set
            self.managed_voice_channels.discard(channel_id)

            # Remove from database
            try:
                await self.cleanup_by_channel_id(channel_id)
            except Exception as e:
                self.logger.exception(
                    "Error cleaning up channel %s in database", channel_id, exc_info=e
                )
            return

        # Channel exists, try to delete it
        try:
            # Delete the channel - handle idempotent 404 errors gracefully
            try:
                delete_method = getattr(channel, "delete", None)
                if isinstance(
                    channel,
                    (
                        discord.VoiceChannel,
                        discord.StageChannel,
                        discord.TextChannel,
                        discord.CategoryChannel,
                    ),
                ) and callable(delete_method):
                    delete_result = delete_method(
                        reason="Empty managed voice channel cleanup"
                    )
                    if isawaitable(delete_result):
                        await delete_result
                    self.logger.info(f"Successfully deleted empty channel {channel_id}")
                elif callable(delete_method):
                    delete_result = delete_method(
                        reason="Empty managed voice channel cleanup"
                    )
                    if isawaitable(delete_result):
                        await delete_result
                    else:
                        # Non-awaitable delete (e.g., simple mock); just invoke
                        self.logger.debug(
                            "Delete method for channel %s returned non-awaitable; considered cleaned",
                            channel_id,
                        )
                    self.logger.info(f"Successfully deleted empty channel {channel_id}")
                else:
                    self.logger.warning(
                        f"Channel {channel_id} is not a deletable guild channel type, skipping"
                    )
            except discord.NotFound:
                # Channel already deleted - this is fine, no stack trace needed
                self.logger.info(f"Channel {channel_id} already deleted during cleanup")
            except discord.Forbidden as e:
                # Insufficient permissions - keep tracking so reconciliation
                # can retry later instead of leaving an unmanaged orphan.
                self.logger.warning(
                    "Insufficient permissions to delete channel %s: %s — "
                    "keeping tracking for retry",
                    channel_id,
                    e,
                )
                return

        except Exception as e:
            self.logger.exception(
                "Unexpected error during channel deletion for %s",
                channel_id,
                exc_info=e,
            )
        finally:
            # Remove from managed channels set and database only when the
            # Discord channel was actually deleted (or already gone).
            # The Forbidden branch returns early to preserve tracking.
            self.managed_voice_channels.discard(channel_id)

            try:
                await self.cleanup_by_channel_id(channel_id)
                self.logger.info(f"Cleaned up tracking for channel {channel_id}")
            except Exception as e:
                self.logger.exception(
                    "Error cleaning up channel %s in database", channel_id, exc_info=e
                )

    async def _handle_join_to_create(
        self,
        guild: discord.Guild,
        jtc_channel: discord.VoiceChannel,
        member: discord.Member,
        *,
        bypass_cooldown: bool = False,
    ) -> None:
        """Handle join-to-create channel logic."""
        try:
            self.logger.info(
                "%s joined JTC channel %s",
                member.display_name,
                jtc_channel.name,
            )

            if self.debug_logging_enabled:
                self.logger.info(
                    "JTC: handle_join guild=%s jtc=%s user=%s creating=%s",
                    guild.id,
                    jtc_channel.id,
                    member.id,
                    self._is_user_creating(guild.id, member.id),
                )

            if self._is_user_creating(guild.id, member.id):
                if self.debug_logging_enabled:
                    self.logger.debug(
                        "Ignoring duplicate event for %s - creation already in progress",
                        member.display_name,
                    )
                return

            # Get per-user creation lock to prevent race conditions
            lock = await self._get_creation_lock(guild.id, member.id)

            if self.debug_logging_enabled:
                self.logger.debug(
                    "Acquired per-user lock for %s (ID: %s) in guild %s",
                    member.display_name,
                    member.id,
                    guild.id,
                )

            creation_marked = False

            async with lock:
                if self._is_user_creating(guild.id, member.id):
                    if self.debug_logging_enabled:
                        self.logger.debug(
                            "Skipping creation for %s; lock-acquired dedupe",
                            member.display_name,
                        )
                    return

                # Double-check cooldown after acquiring lock
                can_create, error_code = await self.can_create_voice_channel(
                    guild.id,
                    jtc_channel.id,
                    member.id,
                    bypass_cooldown=bypass_cooldown,
                )
                if not can_create:
                    # Check if it's because user is already creating
                    if error_code == "CREATING":
                        if self.debug_logging_enabled:
                            self.logger.debug(
                                "Ignoring duplicate creation event for %s - already creating",
                                member.display_name,
                            )
                        return

                    self.logger.info(
                        "Cooldown prevented channel creation for %s: %s",
                        member.display_name,
                        error_code,
                    )
                    if error_code == "COOLDOWN":
                        from helpers.discord_reply import dm_user
                        from helpers.error_messages import format_user_error

                        seconds = await self.config_service.get_guild_setting(
                            guild.id, "voice.cooldown_seconds", 5
                        )
                        message = format_user_error("COOLDOWN", seconds=seconds)
                        await dm_user(member, message)
                    return

                # Mark user as creating to prevent duplicate events during channel creation
                self._mark_user_creating(guild.id, member.id)
                creation_marked = True

                if self.debug_logging_enabled:
                    self.logger.debug(
                        "Marked user %s as creating channel in guild %s",
                        member.id,
                        guild.id,
                    )

                try:
                    # Create a new channel for the user with timeout
                    try:
                        channel: discord.VoiceChannel | None = None
                        if self.debug_logging_enabled:
                            self.logger.info(
                                "JTC: about_to_create guild=%s jtc=%s user=%s",
                                guild.id,
                                jtc_channel.id,
                                member.id,
                            )
                        channel = await asyncio.wait_for(
                            self._create_user_channel(guild, jtc_channel, member),
                            timeout=self.CHANNEL_CREATION_TIMEOUT_SECONDS,
                        )
                        if self.debug_logging_enabled:
                            self.logger.info(
                                "JTC: created_channel_result guild=%s jtc=%s user=%s channel=%s",
                                guild.id,
                                jtc_channel.id,
                                member.id,
                                channel.id if channel else None,
                            )
                    except TimeoutError:
                        self.logger.exception(
                            "Channel creation timed out for %s in JTC %s",
                            member.display_name,
                            jtc_channel.name,
                        )
                        # Notify in bot spam channel
                        await self._notify_bot_spam_channel(
                            guild,
                            f"⚠️ Voice channel creation timed out for {member.mention} - Discord API may be slow",
                        )
                        # Send DM to user
                        try:
                            from helpers.discord_reply import dm_user

                            await dm_user(
                                member,
                                "⚠️ Voice channel creation took too long. Please try again.",
                            )
                        except Exception:
                            self.logger.debug(
                                "DM failure (timeout) for %s",
                                member.id,
                                exc_info=True,
                            )
                finally:
                    # Always unmark user as creating, even if creation fails
                    if creation_marked:
                        self._spawn_background_task(
                            self._delayed_unmark_user_creating(
                                guild.id,
                                member.id,
                                delay=self._creation_unmark_delay,
                            ),
                            name=f"voice.unmark_user.{guild.id}.{member.id}",
                        )

        except Exception as e:
            self.logger.exception("Error handling join-to-create", exc_info=e)

