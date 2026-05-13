"""
VoiceCreateMixin — extracted from services/voice_service.py for size management.

Do not import directly; import VoiceService from services.voice_service.

AI Notes:
    All methods access `self` attributes populated by VoiceService.__init__.
    Python MRO resolves them correctly at runtime.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

import discord  # type: ignore[import-not-found]

from services.db.repository import BaseRepository
from services.voice_base_mixin import VoiceServiceBase
from services.voice_channel_helpers import (
    get_user_game_name,
)


# Module-level alias for test patching (mirrors voice_service.py pattern)
async def update_last_used_jtc_channel(guild_id: int, user_id: int, jtc_channel_id: int) -> None:
    """Alias for test patching — deferred import avoids circular dependency."""
    from helpers.voice_settings import update_last_used_jtc_channel as real_func

    await real_func(guild_id, user_id, jtc_channel_id)


class VoiceCreateMixin(VoiceServiceBase):
    """Mixin for VoiceService — see voice_service.py for full context."""

    async def _create_user_channel(
        self,
        guild: discord.Guild,
        jtc_channel: discord.VoiceChannel,
        member: discord.Member,
    ) -> discord.VoiceChannel | None:
        """Create a new voice channel for a user and return it on success.

        This is the AUTHORITATIVE channel creation path. All voice channel creation
        must route through this function to ensure proper race-condition handling,
        atomic DB operations, and consistent permission enforcement.

        DO NOT call guild.create_voice_channel() directly elsewhere - use this function
        or _handle_join_to_create() which calls this function.
        """
        try:
            self.logger.info(
                "Creating channel for %s (ID: %s) in guild %s, JTC channel %s ('%s')",
                member.display_name,
                member.id,
                guild.id,
                jtc_channel.id,
                jtc_channel.name,
            )

            # Load saved settings from database
            saved_settings = await self._load_channel_settings(
                guild.id, jtc_channel.id, member.id
            )

            # Debug logging to see what settings are loaded
            if self.debug_logging_enabled:
                if saved_settings:
                    self.logger.debug(
                        "Loaded settings for user %s in JTC %s: %d settings",
                        member.id,
                        jtc_channel.id,
                        len(saved_settings),
                    )
                else:
                    self.logger.debug(
                        "No saved settings found for user %s in JTC %s",
                        member.id,
                        jtc_channel.id,
                    )

            # Generate channel name - use saved name if available, otherwise default
            if saved_settings and saved_settings.get("channel_name"):
                channel_name = saved_settings["channel_name"]
                if self.debug_logging_enabled:
                    self.logger.debug("Using saved channel name for user %s", member.id)
            else:
                channel_name = f"{member.display_name}'s Channel"
                if self.debug_logging_enabled:
                    self.logger.debug(
                        "Using default channel name for user %s", member.id
                    )

            # Create the channel in the same category as the JTC channel
            category = jtc_channel.category

            # Determine user limit - use saved limit if available, otherwise JTC default
            if saved_settings and saved_settings.get("user_limit") is not None:
                user_limit = saved_settings["user_limit"]
            else:
                user_limit = jtc_channel.user_limit

            # Check permissions before attempting to create channel
            if category is None:
                raise RuntimeError(f"JTC channel {jtc_channel.name} has no category")

            can_create, error_msg = await self._validate_jtc_permissions(category)
            if not can_create:
                raise RuntimeError(error_msg or "Permission validation failed")

            # Get bot_member for later permission checks
            if not self.bot or not self.bot.user:
                raise RuntimeError("Bot instance not available")
            bot_member = guild.get_member(self.bot.user.id)
            if bot_member is None:
                raise RuntimeError("Bot member not found in guild")

            # Copy permission overwrites from the JTC source channel so
            # the new channel inherits role/user overrides configured on the
            # JTC channel (e.g. muted roles, restricted access).  Base safety
            # permissions (owner, bot, @everyone) and DB-driven custom
            # settings are merged on top by enforce_permission_changes().
            #
            # Discord API restrictions:
            # 1. The bot cannot set overwrites for its own managed/integration
            #    role (Discord rejects this with 403 Forbidden).
            # 2. Overwrites cannot grant permissions the bot itself lacks
            #    in the guild/category (permission value check).
            bot_category_perms = category.permissions_for(bot_member)
            bot_role_ids = {r.id for r in bot_member.roles if not r.is_default()}
            jtc_overwrites: dict[
                discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
            ] = {}
            for target, overwrite in jtc_channel.overwrites.items():
                # Skip the bot's own roles (excluding @everyone) to prevent
                # Forbidden errors — Discord rejects overwrites on a bot's
                # own managed/integration role.
                if isinstance(target, discord.Role) and target.id in bot_role_ids:
                    if self.debug_logging_enabled:
                        self.logger.debug(
                            "Skipping JTC overwrite for bot's own role '%s'",
                            target.name,
                        )
                    continue
                # Filter out permission values the bot cannot grant
                sanitized = self._sanitize_overwrite(overwrite, bot_category_perms)
                jtc_overwrites[target] = sanitized

            # Ensure the bot always has the documented critical creation
            # permissions on the new channel before Discord applies JTC denies.
            bot_creation_overwrite = jtc_overwrites.get(
                bot_member, discord.PermissionOverwrite()
            )
            bot_creation_overwrite.update(
                **self.BOT_CREATION_OVERWRITE_PERMISSIONS
            )
            jtc_overwrites[bot_member] = self._sanitize_overwrite(
                bot_creation_overwrite, bot_category_perms
            )

            # Ensure the channel owner can always connect
            owner_creation_overwrite = jtc_overwrites.get(
                member, discord.PermissionOverwrite()
            )
            owner_creation_overwrite.update(
                **self.OWNER_CREATION_OVERWRITE_PERMISSIONS
            )
            jtc_overwrites[member] = self._sanitize_overwrite(
                owner_creation_overwrite, bot_category_perms
            )

            if self.debug_logging_enabled:
                self.logger.debug(
                    "Copying %d permission overwrites from JTC channel %s",
                    len(jtc_overwrites),
                    jtc_channel.id,
                )

            try:
                channel = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    bitrate=jtc_channel.bitrate,
                    user_limit=user_limit,
                    overwrites=jtc_overwrites,
                )
            except discord.Forbidden:
                # Bulk creation with all JTC overwrites failed — likely due
                # to stale/deleted role overwrites on the JTC source channel.
                # Create with bot + owner overwrites only (1 API call);
                # the channel inherits other permissions from the category
                # and enforce_permission_changes() handles DB-driven settings.
                # This avoids the per-overwrite set_permissions loop that
                # triggers Discord rate limiting and causes timeouts.
                self.logger.warning(
                    "Bulk JTC overwrites rejected for %s — creating with essential overwrites only",
                    member.display_name,
                )
                essential_overwrites: dict[
                    discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
                ] = {
                    bot_member: jtc_overwrites[bot_member],
                    member: jtc_overwrites[member],
                }
                try:
                    channel = await guild.create_voice_channel(
                        name=channel_name,
                        category=category,
                        bitrate=jtc_channel.bitrate,
                        user_limit=user_limit,
                        overwrites=essential_overwrites,
                    )
                except discord.Forbidden:
                    self.logger.warning(
                        "Essential overwrites also rejected for %s — creating bare channel",
                        member.display_name,
                    )
                    channel = await guild.create_voice_channel(
                        name=channel_name,
                        category=category,
                        bitrate=jtc_channel.bitrate,
                        user_limit=user_limit,
                    )

            # Apply all saved settings from database after creation
            if self.bot:
                import services.voice_service as _svc

                await _svc.enforce_permission_changes(
                    channel=channel,
                    bot=self.bot,
                    user_id=member.id,
                    guild_id=guild.id,
                    jtc_channel_id=jtc_channel.id,
                )

            # Validate user is still connected to voice before moving
            if member.voice is None or member.voice.channel is None:
                self.logger.warning(
                    "User %s disconnected before channel creation completed, cleaning up channel %s",
                    member.display_name,
                    channel.id,
                )
                # Cleanup the created channel
                await self._delete_channel_safe(
                    channel, reason="User disconnected during channel creation"
                )

                # Send DM to user
                try:
                    from helpers.discord_reply import dm_user

                    await dm_user(
                        member,
                        "⚠️ Your voice channel was created but you disconnected before it was ready. Please rejoin the Join to Create channel to try again.",
                    )
                except Exception:
                    self.logger.debug(
                        "DM failure (disconnect) for %s",
                        member.id,
                        exc_info=True,
                    )

                # Notify in bot spam channel
                await self._notify_bot_spam_channel(
                    guild,
                    f"⚠️ Voice channel creation aborted for {member.mention} - user disconnected during setup",
                )
                return None

            # Move the user to their new channel BEFORE storing in database
            # This prevents race conditions where concurrent operations see the channel
            # as active before the user is actually in it
            try:
                await member.move_to(channel)
            except discord.HTTPException as e:
                self.logger.exception(
                    "Failed to move %s to channel %s",
                    member.display_name,
                    channel.id,
                    exc_info=e,
                )
                # Cleanup the created channel
                await self._delete_channel_safe(channel, reason="Failed to move user")

                # Send DM to user
                try:
                    from helpers.discord_reply import dm_user

                    await dm_user(
                        member,
                        "⚠️ Failed to move you to your voice channel. You may have disconnected too quickly. Please try again.",
                    )
                except Exception:
                    self.logger.debug(
                        "DM failure (move failed) for %s",
                        member.id,
                        exc_info=True,
                    )

                # Notify in bot spam channel
                await self._notify_bot_spam_channel(
                    guild,
                    f"⚠️ Voice channel creation failed for {member.mention} - could not move user (error: {e})",
                )
                return None

            # Only store in database after successful move
            try:
                await self._store_user_channel(
                    guild.id, jtc_channel.id, member.id, channel.id
                )
            except Exception as e:
                # Move succeeded but DB store failed — the channel exists on
                # Discord but has no tracking record.  Clean it up rather than
                # leave an unmanaged orphan.
                self.logger.exception(
                    "DB store failed after moving %s to channel %s — cleaning up",
                    member.display_name,
                    channel.id,
                    exc_info=e,
                )
                await self._delete_channel_safe(
                    channel, reason="DB store failed after move"
                )
                return None

            # Update cooldown
            await self._update_cooldown(guild.id, jtc_channel.id, member.id)

            # Update last used JTC channel for deterministic settings behavior
            import services.voice_service as _svc2

            await _svc2.update_last_used_jtc_channel(guild.id, member.id, jtc_channel.id)

            # Add to managed channels set
            self.managed_voice_channels.add(channel.id)

            self.logger.info(
                "Created channel '%s' for %s", channel.name, member.display_name
            )

            # Send channel settings view message
            try:
                # Late import to break circular dependency between voice_service and views
                # (views imports voice utilities which depend on voice_service)
                from helpers.views import ChannelSettingsView

                self._spawn_background_task(
                    self._send_settings_message_to_vc(
                        voice_channel=channel,
                        member=member,
                        view=ChannelSettingsView(self.bot),
                    ),
                    name=f"voice.settings_message.{channel.id}",
                )
            except Exception:
                self.logger.exception(
                    "Error sending settings view to '%s'",
                    channel.name,
                )

            return channel

        except discord.Forbidden as e:
            # Specific handling for permission errors
            if "50013" in str(e) or "Missing Permissions" in str(e):
                self.logger.exception(
                    "Permission denied creating channel for %s in '%s'",
                    member.display_name,
                    jtc_channel.category.name
                    if jtc_channel.category
                    else "no category",
                )
                try:
                    await member.send(
                        f"❌ I don't have permission to create voice channels in the **{jtc_channel.category.name if jtc_channel.category else 'current'}** category. "
                        "Please ask a server admin to give me the 'Manage Channels' and 'Manage Permissions' permissions in that category."
                    )
                except Exception:
                    self.logger.debug(
                        "DM failure (permission denied) for %s",
                        member.id,
                        exc_info=True,
                    )
                return None  # Stop execution as channel creation failed
            else:
                self.logger.exception("Discord permission error creating user channel")
                return None
        except Exception:
            self.logger.exception("Error creating user channel")
            return None

    def _get_user_game_name(self, member: discord.Member) -> str | None:
        """Get the user's current game/activity name."""
        return get_user_game_name(member, self.logger)

    async def _handle_old_channel_transition(
        self,
        *,
        db: Any,
        guild_id: int,
        jtc_channel_id: int,
        user_id: int,
        old_channel_id: int,
        new_channel_id: int,
    ) -> discord.VoiceChannel | None:
        """
        Handle transition when a user already has an active channel.

        Returns orphaned channel object when ownership is cleared but members remain.
        """

        old_channel_candidate = (
            self.bot.get_channel(old_channel_id) if self.bot else None
        )
        # Support both real discord channels and mock objects with voice channel interface
        old_channel: discord.VoiceChannel | discord.StageChannel | None = None
        if isinstance(
            old_channel_candidate, (discord.VoiceChannel, discord.StageChannel)
        ):
            old_channel = old_channel_candidate
        elif (
            old_channel_candidate
            and hasattr(old_channel_candidate, "members")
            and hasattr(old_channel_candidate, "edit")
            and hasattr(old_channel_candidate, "overwrites")
        ):
            # Mock object with voice channel interface - cast for type safety
            old_channel = cast("discord.VoiceChannel", old_channel_candidate)

        member_count = self._get_member_count(old_channel or old_channel_id)
        action = self._classify_old_channel(member_count)

        if self.debug_logging_enabled:
            self.logger.info(
                "DB: decision guild=%s jtc=%s user=%s old_channel=%s new_channel=%s action=%s",
                guild_id,
                jtc_channel_id,
                user_id,
                old_channel_id,
                new_channel_id,
                action,
            )

        return await self._handle_orphan_or_delete(
            db=db,
            action=action,
            user_id=user_id,
            old_channel_id=old_channel_id,
            old_channel=old_channel,
        )

    async def _store_user_channel(
        self, guild_id: int, jtc_channel_id: int, user_id: int, channel_id: int
    ) -> None:
        """Store user channel in database with atomic transaction to prevent duplicates.

        Uses explicit transaction with SELECT + INSERT to ensure only one active channel
        per user per JTC exists in the database, preventing TOCTOU race conditions.
        """
        try:
            orphaned_channel: discord.VoiceChannel | None = None
            async with BaseRepository.exclusive_transaction() as db:
                # Check if there's already an active channel for this user in this JTC
                # This SELECT happens inside the transaction, preventing TOCTOU
                cursor = await db.execute(
                    """
                    SELECT voice_channel_id FROM voice_channels
                    WHERE guild_id = ? AND jtc_channel_id = ? AND owner_id = ? AND is_active = 1
                    """,
                    (guild_id, jtc_channel_id, user_id),
                )
                existing_row = await cursor.fetchone()
                existing_channel_id = existing_row[0] if existing_row else None

                if self.debug_logging_enabled:
                    self.logger.info(
                        "DB: store_user_channel guild=%s jtc=%s user=%s existing_channel=%s",
                        guild_id,
                        jtc_channel_id,
                        user_id,
                        existing_channel_id,
                    )

                if existing_row and existing_channel_id is not None:
                    old_channel_id = existing_channel_id
                    if old_channel_id == channel_id:
                        # Same channel, this is a no-op (defensive check)
                        if self.debug_logging_enabled:
                            self.logger.debug(
                                f"DB: Channel {channel_id} already stored for user {user_id}, skipping duplicate insert"
                            )
                        # Context manager will commit on exit
                        return

                    orphaned_channel = await self._handle_old_channel_transition(
                        db=db,
                        guild_id=guild_id,
                        jtc_channel_id=jtc_channel_id,
                        user_id=user_id,
                        old_channel_id=old_channel_id,
                        new_channel_id=channel_id,
                    )

                # Insert the new channel atomically
                await db.execute(
                    """
                    INSERT INTO voice_channels
                    (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        jtc_channel_id,
                        user_id,
                        channel_id,
                        int(time.time()),
                        int(time.time()),
                        1,
                    ),
                )

                # Context manager auto-commits on success

                if self.debug_logging_enabled:
                    self.logger.info(
                        "DB: insert_complete guild=%s jtc=%s user=%s old_channel=%s new_channel=%s",
                        guild_id,
                        jtc_channel_id,
                        user_id,
                        existing_channel_id,
                        channel_id,
                    )

        except Exception as e:
            self.logger.exception("Error storing user channel", exc_info=e)
            orphaned_channel = None  # Ensure it's defined even if exception occurred

        # Remove owner overwrites after transaction commits to avoid blocking DB
        if orphaned_channel:
            await self._remove_owner_overwrites(orphaned_channel, user_id)

    async def _remove_owner_overwrites(
        self, channel: discord.VoiceChannel, owner_id: int
    ) -> None:
        """Strip owner-specific overwrites so the channel truly becomes ownerless."""
        if not channel or not hasattr(channel, "guild"):
            return

        try:
            member = channel.guild.get_member(owner_id)
            if not member:
                return

            # Support both VoiceChannel and mock objects
            if hasattr(channel, "overwrites") and hasattr(channel, "edit"):
                overwrites = (
                    channel.overwrites.copy()
                    if hasattr(channel.overwrites, "copy")
                    else dict(channel.overwrites)
                )
                if member in overwrites:
                    overwrites.pop(member, None)
                    await channel.edit(overwrites=overwrites)
                    if self.debug_logging_enabled:
                        self.logger.info(
                            "Removed overwrites for previous owner %s on orphaned channel %s",
                            owner_id,
                            channel.id,
                        )
        except Exception as exc:
            self.logger.warning(
                "Failed to remove overwrites for owner %s on channel %s: %s",
                owner_id,
                getattr(channel, "id", "unknown"),
                exc,
            )

    async def _schedule_channel_cleanup(self, channel_id: int) -> asyncio.Task:
        """Schedule cleanup of an empty channel after a delay.

        Returns the spawned background task so callers and tests can await the
        full cleanup lifecycle when needed.
        """

        # Get configurable delay from config, default to 10 seconds
        delete_delay = await self.config_service.get_global_setting(
            "voice.delete_delay_seconds", 10
        )

        # Capture references for the cleanup task
        bot = self.bot
        logger = self.logger

        async def cleanup_after_delay():
            await asyncio.sleep(delete_delay)

            try:
                if not bot:
                    logger.warning(
                        f"No bot instance for cleanup of channel {channel_id}"
                    )
                    return

                channel = bot.get_channel(channel_id)
                voice_like: discord.VoiceChannel | None = None
                if isinstance(channel, discord.VoiceChannel):
                    voice_like = channel
                elif hasattr(channel, "members") and hasattr(channel, "delete"):
                    voice_like = cast("discord.VoiceChannel", channel)

                if voice_like and self._get_member_count(voice_like) == 0:
                    # Use the same cleanup path as immediate cleanup
                    await self._cleanup_empty_channel(voice_like)
                elif channel:
                    logger.info(
                        f"Channel {channel_id} no longer empty, skipping cleanup"
                    )
                else:
                    # Channel already deleted or missing, pass channel_id for cleanup
                    await self._cleanup_empty_channel(channel_id)

            except Exception as e:
                logger.exception("Error during scheduled cleanup", exc_info=e)

        # Schedule the cleanup
        return self._spawn_background_task(
            cleanup_after_delay(),
            name=f"voice.cleanup_after_delay.{channel_id}",
        )

