"""
VoiceReconcileMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import discord  # type: ignore[import-not-found]

from services.db.repository import BaseRepository
from services.voice_base_mixin import VoiceServiceBase


class VoiceReconcileMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def _run_reconcile_after_ready(self) -> None:
        """Run reconciliation after bot is ready with configurable delay."""
        try:
            # Wait for bot to be ready
            if self.bot:
                if not hasattr(self.bot, "guilds") or not isinstance(
                    self.bot.guilds, Iterable
                ):
                    self.logger.warning(
                        "Bot guilds collection missing or not iterable; skipping startup reconciliation scheduling"
                    )
                    return

                await self.bot.wait_until_ready()

                # Get configurable delay, default to 2000ms (2 seconds)
                delay_ms = await self.config_service.get_global_setting(
                    "voice.startup_delay_ms", 2000
                )
                await asyncio.sleep(delay_ms / 1000.0)

                # Run the reconciliation
                await self.reconcile_all_guilds_on_ready()

                # After reconciliation, move members back to existing channels (no new creation)
                self._spawn_background_task(
                    self._reconcile_jtc_members_on_startup(),
                    name="voice.reconcile_jtc_members_on_startup",
                )
            else:
                self.logger.warning(
                    "Bot instance not available for startup reconciliation"
                )
        except asyncio.CancelledError:
            self.logger.debug("Reconciliation task cancelled during startup")
        except Exception as e:
            self.logger.exception("Error during startup reconciliation", exc_info=e)

    async def _reconcile_jtc_members_on_startup(self) -> None:
        """
        Reconcile members in JTC channels after bot restart.

        DOES NOT create new channels. Only moves users back to existing channels
        if they have one. Users without existing channels must rejoin the JTC
        channel to trigger creation (prevents startup spam and race conditions).
        """
        try:
            # Ensure bot is ready
            if not self.bot:
                self.logger.warning(
                    "Bot instance not available for JTC member reconciliation"
                )
                return

            await self.bot.wait_until_ready()

            if not hasattr(self.bot, "guilds") or not isinstance(
                self.bot.guilds, Iterable
            ):
                self.logger.warning(
                    "Bot guilds collection missing or not iterable; skipping JTC member reconciliation"
                )
                return

            self.logger.info(
                "Reconciling JTC channel members (no new channel creation)..."
            )

            total_moved = 0
            total_skipped = 0
            total_errors = 0

            # Process each guild the bot is in
            for guild in self.bot.guilds:
                try:
                    # Get JTC channel IDs for this guild
                    jtc_ids = await self.config_service.get_guild_jtc_channels(guild.id)

                    if not jtc_ids:
                        continue

                    # Process each JTC channel
                    for jtc_id in jtc_ids:
                        try:
                            # Try to get channel from cache first, then fetch
                            vc = guild.get_channel(jtc_id)
                            if not vc:
                                try:
                                    vc = await self.bot.fetch_channel(jtc_id)
                                except discord.NotFound:
                                    self.logger.warning(
                                        f"JTC channel {jtc_id} no longer exists in guild {guild.name}"
                                    )
                                    continue
                                except Exception as e:
                                    self.logger.warning(
                                        f"Failed to fetch JTC channel {jtc_id} in guild {guild.name}: {e}"
                                    )
                                    continue

                            # Ensure it's a voice channel
                            if not isinstance(vc, discord.VoiceChannel):
                                self.logger.warning(
                                    f"JTC channel {jtc_id} in guild {guild.name} is not a voice channel"
                                )
                                continue

                            # Process each human member in the JTC channel
                            for member in list(
                                vc.members
                            ):  # Use list() to avoid iteration issues during moves
                                if member.bot:
                                    continue  # Skip bots

                                try:
                                    # Check if user has an existing active channel for this JTC
                                    existing_channel_id = (
                                        await BaseRepository.fetch_value(
                                            """
                                        SELECT voice_channel_id FROM voice_channels
                                        WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
                                        LIMIT 1
                                        """,
                                            (guild.id, jtc_id, member.id),
                                        )
                                    )

                                    if existing_channel_id:
                                        existing_channel = guild.get_channel(
                                            existing_channel_id
                                        )

                                        if existing_channel and isinstance(
                                            existing_channel, discord.VoiceChannel
                                        ):
                                            # Move user back to their existing channel
                                            try:
                                                await member.move_to(existing_channel)
                                                self.logger.info(
                                                    f"Moved {member.display_name} back to existing channel {existing_channel.name}"
                                                )
                                                total_moved += 1
                                            except discord.HTTPException as e:
                                                self.logger.warning(
                                                    f"Failed to move {member.display_name} to existing channel: {e}"
                                                )
                                                total_errors += 1
                                        else:
                                            # Channel in DB but doesn't exist in Discord - clean up
                                            self.logger.info(
                                                f"Cleaning up stale channel reference {existing_channel_id} for user {member.id}"
                                            )
                                            await self.cleanup_by_channel_id(
                                                existing_channel_id
                                            )
                                            total_skipped += 1
                                    else:
                                        # No existing channel - user must rejoin JTC to create one
                                        if self.debug_logging_enabled:
                                            self.logger.debug(
                                                f"User {member.display_name} has no existing channel, must rejoin JTC to create"
                                            )
                                        total_skipped += 1

                                except Exception as e:
                                    self.logger.exception(
                                        f"Failed to reconcile {member.display_name} ({member.id}) in JTC {jtc_id}",
                                        exc_info=e,
                                    )
                                    total_errors += 1

                        except Exception as e:
                            self.logger.exception(
                                f"Error processing JTC channel {jtc_id} in guild {guild.name}",
                                exc_info=e,
                            )
                            total_errors += 1

                except Exception as e:
                    self.logger.exception(
                        f"Error processing guild {guild.name} ({guild.id}) for JTC reconciliation",
                        exc_info=e,
                    )

            self.logger.info(
                f"JTC member reconciliation complete: {total_moved} moved to existing channels, "
                f"{total_skipped} skipped (no existing channel), {total_errors} errors"
            )

        except Exception as e:
            self.logger.exception("Error during JTC member reconciliation", exc_info=e)

    async def reconcile_all_guilds_on_ready(self) -> None:
        """
        Reconcile all user voice channels after bot ready and member chunking.


        For each guild the bot is in:
        - Fetch all rows from voice_channels
        - Check if channels still exist
        - If not exists → remove DB row
        - If exists and has members or owner connected → keep and rehydrate management
        - If exists but empty → schedule deletion with delay
        """
        if not self.bot:
            self.logger.warning("Bot instance not available for reconciliation")
            return

        self.logger.info("Starting voice channel reconciliation across all guilds")

        deleted_inactive = await self._purge_inactive_voice_channels()
        if deleted_inactive:
            self.logger.info(
                f"Purged {deleted_inactive} inactive voice channel rows before reconciliation"
            )

        total_reconciled = 0
        total_removed = 0
        total_rehydrated = 0
        total_scheduled_cleanup = 0

        try:
            # Fetch all user voice channels across all guilds
            all_channels = await BaseRepository.fetch_all(
                """SELECT guild_id, voice_channel_id, owner_id, jtc_channel_id, created_at
                   FROM voice_channels WHERE is_active = 1""",
            )

            for (
                guild_id,
                voice_channel_id,
                owner_id,
                jtc_channel_id,
                created_at,
            ) in all_channels:
                try:
                    await self._reconcile_single_channel(
                        guild_id,
                        voice_channel_id,
                        owner_id,
                        jtc_channel_id,
                        created_at,
                    )
                    total_reconciled += 1

                    # Track reconciliation results based on what happened
                    channel = self.bot.get_channel(voice_channel_id)
                    if not channel:
                        total_removed += 1
                    elif voice_channel_id in self.managed_voice_channels:
                        total_rehydrated += 1
                    else:
                        total_scheduled_cleanup += 1

                except Exception as e:
                    self.logger.exception(
                        f"Error reconciling channel {voice_channel_id} (guild {guild_id})",
                        exc_info=e,
                    )

        except Exception as e:
            self.logger.exception(
                "Error during voice channel reconciliation", exc_info=e
            )

        self.logger.info(
            f"Voice channel reconciliation complete: {total_reconciled} channels processed, "
            f"{total_removed} removed, {total_rehydrated} rehydrated, {total_scheduled_cleanup} scheduled for cleanup"
        )

    async def _reconcile_single_channel(
        self,
        guild_id: int,
        voice_channel_id: int,
        owner_id: int,
        jtc_channel_id: int,
        created_at: int,
    ) -> None:
        """
        Reconcile a single voice channel during startup.

        Args:
            guild_id: Discord guild ID
            voice_channel_id: Voice channel ID to reconcile
            owner_id: Channel owner ID
            jtc_channel_id: JTC channel ID this channel belongs to
            created_at: Timestamp when channel was created
        """
        # Try to get the channel, first from cache then fetch
        if not self.bot:
            self.logger.warning("Bot instance not available for reconciliation")
            await self.cleanup_by_channel_id(voice_channel_id)
            return

        channel = self.bot.get_channel(voice_channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(voice_channel_id)
            except discord.NotFound:
                channel = None
            except Exception as e:
                self.logger.warning(f"Failed to fetch channel {voice_channel_id}: {e}")
                channel = None

        # Channel no longer exists - remove DB row
        if not channel:
            self.logger.info(f"Removing stale channel {voice_channel_id} from database")
            await self.cleanup_by_channel_id(voice_channel_id)
            return

        # Channel still exists - determine what to do based on emptiness and ownership
        if not isinstance(channel, discord.VoiceChannel):
            self.logger.warning(
                f"Channel {voice_channel_id} is not a VoiceChannel, removing from database"
            )
            await self.cleanup_by_channel_id(voice_channel_id)
            return

        should_keep_active = await self._should_keep_channel_active(channel, owner_id)

        if should_keep_active:
            # Add to managed channels and rehydrate settings when we still have an owner
            self.managed_voice_channels.add(voice_channel_id)
            if owner_id != self.ORPHAN_OWNER_ID:
                await self._rehydrate_channel_management(
                    channel, owner_id, jtc_channel_id, guild_id
                )
                self.logger.info(
                    f"Rehydrated channel {voice_channel_id} for owner {owner_id} with {len(channel.members)} members."
                )
            else:
                self.logger.info(
                    f"Skipped rehydration for orphaned channel {voice_channel_id}; members will need to claim ownership."
                )
        else:
            # Check startup cleanup mode (immediate vs delayed)
            startup_cleanup_mode = await self.config_service.get_global_setting(
                "voice.startup_cleanup_mode", "delayed"
            )

            if startup_cleanup_mode == "immediate":
                channel_name = getattr(channel, "name", str(voice_channel_id))
                self.logger.info(
                    f"Immediately cleaning up empty channel {channel_name} ({voice_channel_id}) per startup_cleanup_mode"
                )
                await self._cleanup_empty_channel(voice_channel_id)
            else:
                # Schedule deletion with delay to handle race conditions
                channel_name = getattr(channel, "name", str(voice_channel_id))
                self.logger.info(
                    f"Scheduling cleanup for empty channel {channel_name} ({voice_channel_id})"
                )
                await self._schedule_channel_cleanup(voice_channel_id)

    async def _should_keep_channel_active(
        self, channel: discord.VoiceChannel, owner_id: int
    ) -> bool:
        """
        Determine if a channel should be kept active during reconciliation.

        Returns True if:
        - Channel has members, OR
        - Channel owner is actually connected to that channel
        """
        # Check if channel has any members
        if self._get_member_count(channel) > 0:
            return True

        # Check if owner is connected to this specific channel
        try:
            guild = channel.guild
            owner = guild.get_member(owner_id)
            if (
                owner
                and owner.voice
                and owner.voice.channel
                and owner.voice.channel.id == channel.id
            ):
                return True
        except Exception as e:
            self.logger.warning(
                f"Error checking owner connection for channel {channel.id}: {e}"
            )

        return False

    async def _rehydrate_channel_management(
        self,
        channel: discord.VoiceChannel,
        owner_id: int,
        jtc_channel_id: int,
        guild_id: int,
    ) -> None:
        """
        Rehydrate channel management by applying stored settings and permissions.

        Args:
            channel: Discord voice channel
            owner_id: Channel owner ID
            jtc_channel_id: JTC channel ID
            guild_id: Guild ID
        """
        try:
            # Late import to break circular dependency between voice_service and voice_permissions
            # (voice_permissions imports discord_api which may depend on voice_service)
            from helpers.voice_permissions import enforce_permission_changes

            # Re-apply channel overwrites/settings using existing helpers
            # Signature: enforce_permission_changes(channel, bot, user_id, guild_id, jtc_channel_id)
            if self.bot:
                await enforce_permission_changes(
                    channel, self.bot, owner_id, guild_id, jtc_channel_id
                )

            self.logger.info(
                f"Applied permission overwrites for channel {channel.name} ({channel.id}) owner {owner_id}"
            )

        except Exception as e:
            self.logger.exception(
                f"Error rehydrating channel management for {channel.id}", exc_info=e
            )

