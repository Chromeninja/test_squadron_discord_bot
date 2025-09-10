# cogs/voice.py

"""
Voice Cog

This cog manages dynamic voice channels for the Discord bot. It handles:
  - Creation and deletion of managed channels via a 'Join to Create' channel.
  - Automatic application of stored settings (such as role-based permit/reject,
    PTT, Priority Speaker, and Soundboard) when a new channel is created.
  - A set of slash commands for managing channel settings, permissions, and administration.
"""

import asyncio
import json
import os
import time

import discord
from discord import app_commands
from discord.ext import commands

from config.config_loader import ConfigLoader
from helpers.database import Database
from helpers.discord_api import (
    channel_send_message,
    create_voice_channel,
    delete_channel,
    edit_channel,
    followup_send_message,
    move_member,
    send_direct_message,
    send_message,
)
from helpers.logger import get_logger
from helpers.permissions_helper import (
    fetch_permit_reject_entries,
    update_channel_owner,
)
from helpers.views import ChannelSettingsView
from helpers.voice_repo import (
    cleanup_legacy_user_voice_data,
    cleanup_user_voice_data,
    get_stale_voice_entries,
)
from helpers.voice_utils import (
    create_voice_settings_embed,
    fetch_channel_settings,
    format_channel_settings,
    get_user_channel,
    get_user_game_name,
)
from utils.tasks import spawn

logger = get_logger(__name__)


class Voice(commands.GroupCog, name="voice"):
    """
    Cog for managing dynamic voice channels.
    """

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.bot_admin_role_ids = [
            int(r) for r in self.config["roles"].get("bot_admins", [])
        ]
        self.lead_moderator_role_ids = [
            int(r) for r in self.config["roles"].get("lead_moderators", [])
        ]
        self.cooldown_seconds = self.config["voice"].get("cooldown_seconds", 60)
        self.expiry_days = self.config["voice"].get("expiry_days", 30)

        # Dictionary to store JTC channels per guild
        self.guild_jtc_channels = {}
        # Dictionary to store voice categories per guild
        self.guild_voice_categories = {}

        # Legacy attributes (kept for backward compatibility)
        self.join_to_create_channel_ids = []
        self.voice_category_id = None

        self.managed_voice_channels = set()
        self.last_channel_edit = {}
        self._voice_event_locks = {}

    async def cog_load(self) -> None:
        """
        Called when the cog is loaded.
        Fetch stored settings (such as join-to-create channel IDs and voice category)
        and reconcile previously managed voice channels.
        """
        # Load guild settings from the new guild_settings table
        async with Database.get_connection() as db:
            # Load guild-specific join-to-create channels
            cursor = await db.execute(
                "SELECT guild_id, key, value FROM guild_settings WHERE key = ?",
                ("join_to_create_channel_ids",),
            )
            rows = await cursor.fetchall()
            for row in rows:
                guild_id = row[0]
                value = json.loads(row[2])
                self.guild_jtc_channels[guild_id] = value

            # Load guild-specific voice categories
            cursor = await db.execute(
                "SELECT guild_id, key, value FROM guild_settings WHERE key = ?",
                ("voice_category_id",),
            )
            rows = await cursor.fetchall()
            for row in rows:
                guild_id = row[0]
                value = int(row[2])
                self.guild_voice_categories[guild_id] = value

            # Fall back to legacy settings if no guild settings exist
            if not self.guild_jtc_channels:
                cursor = await db.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    ("join_to_create_channel_ids",),
                )
                if row := await cursor.fetchone():
                    self.join_to_create_channel_ids = json.loads(row[0])
                    # For legacy compatibility, add to first guild
                    if self.bot.guilds and self.join_to_create_channel_ids:
                        first_guild_id = self.bot.guilds[0].id
                        self.guild_jtc_channels[first_guild_id] = (
                            self.join_to_create_channel_ids
                        )

            if not self.guild_voice_categories:
                cursor = await db.execute(
                    "SELECT value FROM settings WHERE key = ?", ("voice_category_id",)
                )
                if row := await cursor.fetchone():
                    self.voice_category_id = int(row[0])
                    # For legacy compatibility, add to first guild
                    if self.bot.guilds and self.voice_category_id:
                        first_guild_id = self.bot.guilds[0].id
                        self.guild_voice_categories[first_guild_id] = (
                            self.voice_category_id
                        )

        # Reconcile managed channels on startup (non-blocking)
        # Use the central reconciliation routine which will inspect stored
        # channels, keep those with members, delete empty channels, and
        # remove DB rows for missing channels.
        spawn(self.reconcile_managed_channels())
        # Start periodic cleanup loop for stale voice channel data.
        spawn(self.channel_data_cleanup_loop())
        logger.info(
            "Voice cog loaded; scheduled reconciliation of managed voice channels."
        )

    async def reconcile_managed_channels(self) -> None:
        """
        Reconcile stored managed channels on startup:
        - If a stored voice channel no longer exists -> delete the DB row.
        - If it exists and is empty -> delete the channel, then delete the DB row.
        - If it exists and has members -> keep it and add to self.managed_voice_channels.

        Logs a summary of kept/removed/missing entries.
        """
        await self.bot.wait_until_ready()

        kept = 0
        removed_empty = 0
        missing_cleaned = 0

        # Snapshot stored channel IDs
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT voice_channel_id FROM user_voice_channels"
            )
            rows = await cursor.fetchall()
            channel_ids = [cid for (cid,) in rows]

        for channel_id in channel_ids:
            channel = None
            try:
                channel = self.bot.get_channel(
                    channel_id
                ) or await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                channel = None
            except Exception as e:
                logger.warning(
                    f"Reconcile: failed to fetch channel ID {channel_id}: {e}"
                )
                channel = None

            if not channel:
                # Channel missing -> remove DB row
                async with Database.get_connection() as db:
                    await db.execute(
                        "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                        (channel_id,),
                    )
                    await db.commit()
                self.managed_voice_channels.discard(channel_id)
                missing_cleaned += 1
                continue

            # Channel exists; check members
            try:
                member_count = len(channel.members)
            except Exception:
                member_count = 0

            if member_count > 0:
                # Keep and manage
                self.managed_voice_channels.add(channel.id)
                kept += 1
                continue

            # Empty -> delete channel and DB row
            try:
                await delete_channel(channel)
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.exception(
                    f"Reconcile: missing permissions to delete channel ID {channel.id}"
                )
            except discord.HTTPException as e:
                logger.exception(
                    f"Reconcile: HTTP error deleting channel ID {channel.id}: {e}"
                )
            finally:
                async with Database.get_connection() as db:
                    await db.execute(
                        "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                        (channel.id,),
                    )
                    await db.commit()
                self.managed_voice_channels.discard(channel.id)
                removed_empty += 1

        logger.info(
            f"Voice reconcile summary: kept={kept}, removed_empty={removed_empty}, missing_cleaned={missing_cleaned}"
        )

    async def cleanup_voice_channel(self, channel_id) -> None:
        """
        Deletes a managed voice channel and removes its record from the database.
        """
        async with Database.get_connection() as db:
            try:
                channel = self.bot.get_channel(
                    channel_id
                ) or await self.bot.fetch_channel(channel_id)
                if channel:
                    logger.info(
                        f"Deleting managed voice channel: {channel.name} (ID: {channel.id})"
                    )
                    await delete_channel(channel)
                else:
                    logger.warning(f"Channel with ID {channel_id} not found.")
            except discord.NotFound:
                logger.warning(
                    f"Channel with ID {channel_id} not found; assumed already deleted."
                )
            except discord.Forbidden:
                logger.exception(
                    f"Bot lacks permissions to delete channel ID {channel_id}."
                )
            except discord.HTTPException as e:
                logger.exception(
                    f"HTTP exception occurred while deleting channel ID {channel_id}: {e}"
                )
            finally:
                await db.execute(
                    "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                    (channel_id,),
                )
                await db.commit()
                logger.info(f"Removed channel ID {channel_id} from the database.")

    async def reconcile_voice_channel(self, channel_id: int) -> None:
        """
        Startup reconciliation for a stored managed channel.

        - If the channel no longer exists -> drop the DB row.
        - If the channel exists and has members -> keep managing it.
        - If the channel exists but is empty -> delete the channel and drop the DB row.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel_id,),
            )
            row = await cursor.fetchone()
            owner_id = row[0] if row else None

        channel = None
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(
                channel_id
            )
        except discord.NotFound:
            channel = None
        except Exception as e:
            logger.warning(
                f"Failed to fetch channel ID {channel_id} during reconciliation: {e}"
            )

        logger.info(f"Reconciling stored channel ID {channel_id}, owner={owner_id}")

        # Channel doesn't exist -> remove stale DB row
        if not channel:
            async with Database.get_connection() as db:
                await db.execute(
                    "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                    (channel_id,),
                )
                await db.commit()
            self.managed_voice_channels.discard(channel_id)
            logger.info(f"Removed stale DB entry for missing channel ID {channel_id}.")
            return

        # Channel exists
        try:
            member_count = len(channel.members)
        except Exception:
            member_count = 0

        # If channel has active members, resume management
        if member_count > 0:
            self.managed_voice_channels.add(channel.id)
            logger.info(
                f"Resuming management of existing channel '{channel.name}' (ID: {channel.id}) "
                f"with {member_count} member(s)."
            )
            return

        # Member cache may not be ready immediately after startup. If the DB lists an owner,
        # check whether the owner is actually connected to this channel (try a few times).
        if owner_id:
            tries = 5
            for _attempt in range(tries):
                try:
                    owner = channel.guild.get_member(
                        owner_id
                    ) or await channel.guild.fetch_member(owner_id)
                except discord.NotFound:
                    owner = None
                except Exception:
                    owner = None

                if (
                    owner
                    and owner.voice
                    and owner.voice.channel
                    and owner.voice.channel.id == channel.id
                ):
                    # Owner is present in the channel — resume management.
                    self.managed_voice_channels.add(channel.id)
                    logger.info(
                        f"Resuming management of channel '{channel.name}' (ID: {channel.id}) because owner is present."
                    )
                    return

                # Re-check members list briefly to account for chunking delays.
                try:
                    member_count = len(channel.members)
                except Exception:
                    member_count = 0
                if member_count > 0:
                    self.managed_voice_channels.add(channel.id)
                    logger.info(

                            f"Resuming management of existing channel '{channel.name}' (ID: {channel.id}) "
                            + "after members appeared."

                    )
                    return

                await asyncio.sleep(2)

            # Channel exists but appears empty — schedule a delayed re-check before deleting
            logger.info(

                    f"Channel '{channel.name}' (ID: {channel.id}) appears empty on "
                    + "reconciliation; scheduling re-check before deletion."

            )
        # Schedule a delayed check to avoid acting on transient empty views
        spawn(self._schedule_deletion_if_still_empty(channel.id, delay=30))

    async def _schedule_deletion_if_still_empty(self, channel_id: int, delay: int = 30) -> None:
        """
        Wait `delay` seconds and delete the channel only if it is still empty and not occupied by its owner.
        Uses the existing cleanup_voice_channel helper to perform the deletion and DB cleanup.
        """
        await asyncio.sleep(delay)
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(
                channel_id
            )
        except discord.NotFound:
            channel = None
        except Exception as e:
            logger.warning(
                f"Error fetching channel ID {channel_id} during scheduled deletion check: {e}"
            )
            channel = None

        if not channel:
            # Nothing to do; ensure DB row removed.
            async with Database.get_connection() as db:
                await db.execute(
                    "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                    (channel_id,),
                )
                await db.commit()
            self.managed_voice_channels.discard(channel_id)
            logger.info(
                f"Scheduled deletion: removed stale DB entry for missing channel ID {channel_id}."
            )
            return

        # If members appeared, resume management
        try:
            member_count = len(channel.members)
        except Exception:
            member_count = 0

        owner_present = False
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel_id,),
            )
            row = await cursor.fetchone()
            owner_id = row[0] if row else None
        if owner_id:
            try:
                owner = channel.guild.get_member(
                    owner_id
                ) or await channel.guild.fetch_member(owner_id)
            except Exception:
                owner = None
            if (
                owner
                and owner.voice
                and owner.voice.channel
                and owner.voice.channel.id == channel.id
            ):
                owner_present = True

        if member_count > 0 or owner_present:
            self.managed_voice_channels.add(channel.id)
            logger.info(

                    f"Scheduled deletion canceled: channel '{channel.name}' (ID: {channel.id}) "
                    + "is now occupied; resuming management."

            )
            return

        # Still empty -> perform deletion & DB cleanup
        logger.info(
            f"Scheduled deletion: channel '{channel.name}' (ID: {channel.id}) "
            f"still empty after {delay}s; deleting."
        )
        try:
            await self.cleanup_voice_channel(channel.id)
        except Exception as e:
            logger.exception(
                f"Error during scheduled cleanup of channel ID {channel.id}: {e}"
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """
        Handles voice state updates.
          - When a user leaves a managed channel and it becomes empty, the channel is deleted.
          - When a user joins a designated 'Join to Create' channel, a new managed channel is created,
            configured with stored settings (including permit/reject, PTT, Priority Speaker, and Soundboard).
        """
        logger.debug(
            f"Voice state update for {member.display_name}: before={before.channel}, after={after.channel}"
        )

        # Serialize voice events per guild to avoid races during channel create/delete operations.
        guild = member.guild
        guild_id = guild.id
        lock = self._voice_event_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            # Handle user leaving a managed channel.
            if before.channel and before.channel.id in self.managed_voice_channels:
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT guild_id, jtc_channel_id, owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                        (before.channel.id,),
                    )
                    row = await cursor.fetchone()
                    owner_id = row[2] if row else None

                    if before.channel and len(before.channel.members) == 0:
                        try:
                            guild = before.channel.guild
                            await guild.fetch_channel(before.channel.id)
                            await delete_channel(before.channel)
                            self.managed_voice_channels.discard(before.channel.id)
                            await db.execute(
                                "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                                (before.channel.id,),
                            )
                            await db.commit()
                            logger.info(
                                f"Deleted empty voice channel '{before.channel.name}'"
                            )
                        except discord.NotFound:
                            logger.warning(
                                f"Channel '{before.channel.id}' not found. Likely already deleted by admin reset."
                            )
                    elif member.id == owner_id:
                        logger.info(
                            f"Owner '{member.display_name}' left '{before.channel.name}'. Ownership can be claimed."
                        )

        # Handle user joining a 'Join to Create' channel.
        # Check both guild-specific and legacy channel IDs
        guild_jtc_channels = self.guild_jtc_channels.get(guild_id, [])
        legacy_jtc = self.join_to_create_channel_ids or []
        is_jtc_channel = after.channel and (
            after.channel.id in guild_jtc_channels or after.channel.id in legacy_jtc
        )

        if after.channel and is_jtc_channel:
            # Find the voice category for this guild
            voice_category_id = self.guild_voice_categories.get(
                guild_id, self.voice_category_id
            )
            if not voice_category_id:
                logger.error(
                    "Voice setup is incomplete. Please run /voice setup command."
                )
                return

            # Prevent duplicate channel creation if user is already in a managed channel.
            if (
                member.voice
                and member.voice.channel
                and member.voice.channel.id in self.managed_voice_channels
            ):
                logger.debug(
                    f"User '{member.display_name}' is already in a managed channel. Skipping creation."
                )
                return

            # Check channel creation cooldown.
            current_time = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT timestamp FROM voice_cooldowns WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (member.id, guild_id, after.channel.id),
                )
                cooldown_row = await cursor.fetchone()
                if cooldown_row:
                    last_created = cooldown_row[0]
                    elapsed_time = current_time - last_created
                    if elapsed_time < self.cooldown_seconds:
                        remaining_time = self.cooldown_seconds - elapsed_time
                        try:
                            await send_direct_message(
                                member,
                                f"You're creating channels too quickly. Please wait {remaining_time} seconds.",
                            )
                        except Exception as e:
                            logger.warning(f"Failed to DM {member.display_name}: {e}")
                        return

            # Create a new managed voice channel.
            try:
                join_to_create_channel = after.channel
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT channel_name, user_limit, lock FROM channel_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                        (member.id, guild_id, after.channel.id),
                    )
                    settings_row = await cursor.fetchone()

                # Determine channel name.
                if settings_row and settings_row[0]:
                    channel_name = settings_row[0]
                else:
                    channel_name = (
                        get_user_game_name(member) or f"{member.display_name}'s Channel"
                    )
                channel_name = channel_name[:32]

                new_channel = await join_to_create_channel.clone(name=channel_name)

                # Build initial overwrites based on the cloned channel.
                final_overwrites = new_channel.overwrites.copy()
                final_overwrites[member] = discord.PermissionOverwrite(
                    manage_channels=True, connect=True
                )
                edit_kwargs = {}
                if settings_row and settings_row[1] is not None:
                    edit_kwargs["user_limit"] = settings_row[1]

                # --- Apply Lock Setting ---
                if settings_row and settings_row[2] == 1:
                    default_role = new_channel.guild.default_role
                    ow = final_overwrites.get(
                        default_role, discord.PermissionOverwrite()
                    )
                    ow.connect = False
                    final_overwrites[default_role] = ow

                # --- Apply Stored Permit/Reject Settings ---
                permit_entries = await fetch_permit_reject_entries(
                    member.id, guild_id, after.channel.id
                )
                for target_id, target_type, perm_action in permit_entries:
                    desired_connect = perm_action == "permit"
                    target = None
                    if target_type == "user":
                        target = new_channel.guild.get_member(target_id)
                    elif target_type == "role":
                        target = new_channel.guild.get_role(target_id)
                    elif target_type == "everyone":
                        target = new_channel.guild.default_role
                    if target:
                        ow = final_overwrites.get(target, discord.PermissionOverwrite())
                        ow.connect = desired_connect
                        final_overwrites[target] = ow

                # --- Apply Additional Voice Feature Settings in Batch ---
                async def apply_feature(table_name: str, feature_key: str) -> None:
                    async with Database.get_connection() as db:
                        column_map = {
                            "ptt": "ptt_enabled",
                            "priority_speaker": "priority_enabled",
                            "soundboard": "soundboard_enabled",
                        }
                        column_name = column_map.get(
                            feature_key, f"{feature_key}_enabled"
                        )
                        query = (
                            "SELECT target_id, target_type, "
                            + column_name
                            + " FROM "
                            + table_name
                            + " WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?"
                        )
                        cursor = await db.execute(
                            query, (member.id, guild_id, after.channel.id)
                        )
                        entries = await cursor.fetchall()
                    for target_id, target_type, enabled in entries:
                        # Convert stored value to Boolean.
                        enabled = bool(enabled)
                        logger.info(

                                f"{feature_key.capitalize()} setting for target {target_id} "
                                f"({target_type}) is stored as: {enabled}"

                        )

                        # Process PTT and Priority Speaker settings.
                        target = None
                        if target_type == "user":
                            target = new_channel.guild.get_member(target_id)
                        elif target_type == "role":
                            target = new_channel.guild.get_role(target_id)
                        elif target_type == "everyone":
                            target = new_channel.guild.default_role
                        if target is None:
                            logger.warning(
                                f"Could not find target {target_id} of type {target_type}"
                            )
                            continue

                        from helpers.permissions_helper import FEATURE_CONFIG

                        cfg = FEATURE_CONFIG.get(feature_key)
                        if not cfg:
                            logger.warning(
                                f"No configuration found for feature {feature_key}"
                            )
                            continue
                        prop = cfg["overwrite_property"]
                        final_value = (
                            not enabled if cfg.get("inverted", False) else enabled
                        )
                        ow = final_overwrites.get(target, discord.PermissionOverwrite())
                        setattr(ow, prop, final_value)
                        final_overwrites[target] = ow

                # Process feature settings for PTT, Priority Speaker, and Soundboard.
                await apply_feature("channel_ptt_settings", "ptt")
                await apply_feature(
                    "channel_priority_speaker_settings", "priority_speaker"
                )
                await apply_feature("channel_soundboard_settings", "soundboard")

                # --- Apply All Updates in a Single Edit Call ---
                edit_kwargs["overwrites"] = final_overwrites
                await move_member(member, new_channel)
                await edit_channel(new_channel, **edit_kwargs)
                msg = (
                    f"Applied all permission and feature settings to "
                    f"'{new_channel.name}' in one batch."
                )
                logger.info(msg)

                # Store channel and update cooldown.
                async with Database.get_connection() as db:
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO user_voice_channels
                        (guild_id, jtc_channel_id, voice_channel_id, owner_id)
                        VALUES (?, ?, ?, ?)
                        """,
                        (guild_id, after.channel.id, new_channel.id, member.id),
                    )
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO voice_cooldowns
                        (guild_id, jtc_channel_id, user_id, timestamp)
                        VALUES (?, ?, ?, ?)
                        """,
                        (guild_id, after.channel.id, member.id, current_time),
                    )
                    await db.commit()
                self.managed_voice_channels.add(new_channel.id)
                logger.info(

                        f"Created voice channel '{new_channel.name}' for "
                        f"{member.display_name} in guild {guild_id}"

                )

                # --- Send Channel Settings View ---
                try:
                    view = ChannelSettingsView(self.bot)
                    await channel_send_message(
                        new_channel,
                        f"{member.mention}, configure your channel settings:",
                        view=view,
                    )
                except discord.Forbidden:
                    logger.warning(f"Cannot send message to '{new_channel.name}'.")
                except Exception as e:
                    logger.exception(
                        f"Error sending settings view to '{new_channel.name}': {e}"
                    )

                # Wait for the channel to become empty in the background so we don't block the
                # on_voice_state_update listener and delay other voice events.
                spawn(self._wait_for_channel_empty(new_channel))
            except Exception as e:
                logger.exception(
                    f"Error creating voice channel for {member.display_name}: {e}"
                )

    async def channel_data_cleanup_loop(self) -> None:
        """
        Runs immediately and then every 24 hours to remove stale channel data
        for users who have not created a channel in the specified expiry period.
        """
        await self.cleanup_stale_channel_data()
        while not self.bot.is_closed():
            await asyncio.sleep(24 * 60 * 60)  # Sleep for 24 hours.
            await self.cleanup_stale_channel_data()

    async def cleanup_stale_channel_data(self) -> None:
        """
        Removes stale data for users who haven't created a channel within the expiry period.
        Uses fully scoped (guild_id, jtc_channel_id, user_id) deletion by default,
        with fallback to legacy user_id-only deletion if USE_LEGACY_CLEANUP is set.
        """
        expiry_seconds = self.expiry_days * 24 * 60 * 60
        cutoff_time = int(time.time() - expiry_seconds)
        logger.info(f"Running stale channel data cleanup (cutoff={cutoff_time}).")

        # Check for feature flag to enable legacy cleanup
        use_legacy_cleanup = (
            os.environ.get("USE_LEGACY_CLEANUP", "false").lower() == "true"
        )

        if use_legacy_cleanup:
            logger.info("Using legacy cleanup (user_id only)")
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT user_id FROM voice_cooldowns WHERE timestamp < ?",
                    (cutoff_time,),
                )
                rows = await cursor.fetchall()
                stale_user_ids = [row[0] for row in rows]
                if not stale_user_ids:
                    logger.info("No stale voice channel data found.")
                    return

                logger.info(f"Found {len(stale_user_ids)} stale user(s) to clean up.")
                for user_id in stale_user_ids:
                    try:
                        await cleanup_legacy_user_voice_data(user_id)
                        logger.info(f"Cleaned stale data for user_id={user_id}")
                    except Exception as e:
                        logger.exception(
                            f"Error cleaning stale data for user_id={user_id}: {e}"
                        )
        else:
            # New scoped cleanup approach
            logger.info("Using scoped cleanup (guild_id, jtc_channel_id, user_id)")
            stale_entries = await get_stale_voice_entries(cutoff_time)
            if not stale_entries:
                logger.info("No stale voice channel data found.")
                return

            logger.info(f"Found {len(stale_entries)} stale entries to clean up.")
            for guild_id, jtc_channel_id, user_id in stale_entries:
                try:
                    await cleanup_user_voice_data(guild_id, jtc_channel_id, user_id)
                    logger.info(
                        f"Cleaned stale data for guild={guild_id}, jtc={jtc_channel_id}, user={user_id}"
                    )
                except Exception as e:
                    logger.exception(
                        f"Error cleaning stale data for guild={guild_id}, jtc={jtc_channel_id}, user={user_id}: {e}"
                    )
        logger.info("Stale channel data cleanup completed.")

    async def _wait_for_channel_empty(self, channel: discord.VoiceChannel) -> None:
        """
        Wait until the provided channel is empty (no members). Runs in background.

        This implementation is resilient: it exits if the bot is shutting down or
        if the channel is deleted or becomes unavailable.
        """
        while not self.bot.is_closed():
            await asyncio.sleep(5)
            # Channel might have been deleted; try to resolve it safely.
            try:
                ch = channel.guild.get_channel(
                    channel.id
                ) or await channel.guild.fetch_channel(channel.id)
            except discord.NotFound:
                return
            except Exception:
                ch = None
            if not ch:
                return
            # If no members remain, exit and allow the scheduled cleanup or other flows to handle deletion.
            if not ch.members:
                return

    # ---------------------------
    # Slash Commands
    # ---------------------------

    @app_commands.command(
        name="list",
        description="List all custom permissions and settings in your voice channel.",
    )
    @app_commands.guild_only()
    async def list_channel_settings(self, interaction: discord.Interaction) -> None:
        """
        Lists the saved channel settings and permissions in an embed.
        """
        settings = await fetch_channel_settings(self.bot, interaction)
        if not settings:
            return
        formatted = format_channel_settings(settings, interaction)
        embed = create_voice_settings_embed(
            settings=settings,
            formatted=formatted,
            title="Channel Settings & Permissions",
            footer="Use /voice commands or the dropdown menu to adjust these settings.",
        )
        await send_message(interaction, "", embed=embed, ephemeral=True)

    @app_commands.command(
        name="claim",
        description="Claim ownership of the voice channel if the owner is absent.",
    )
    @app_commands.guild_only()
    async def claim_channel(self, interaction: discord.Interaction) -> None:
        """
        Allows a user to claim ownership of a voice channel if the original owner is absent.
        """
        member = interaction.user
        channel = member.voice.channel if member.voice else None
        if not channel:
            await send_message(
                interaction,
                "You are not connected to any voice channel.",
                ephemeral=True,
            )
            return

        if channel.id not in self.managed_voice_channels:
            await send_message(
                interaction, "This channel cannot be claimed.", ephemeral=True
            )
            return

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel.id,),
            )
            row = await cursor.fetchone()
            if not row:
                await send_message(
                    interaction,
                    "Unable to retrieve channel ownership information.",
                    ephemeral=True,
                )
                return
            owner_id = row[0]

        owner_in_channel = any(u.id == owner_id for u in channel.members)
        if owner_in_channel:
            logger.warning(
                f"{member.display_name} attempted to claim '{channel.name}' but owner is present."
            )
            await send_message(
                interaction,
                "The channel owner is still present. You cannot claim ownership.",
                ephemeral=True,
            )
            return

        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
                (member.id, channel.id),
            )
            await db.commit()

        try:
            from helpers.views import ChannelSettingsView

            view = ChannelSettingsView(self.bot)
            await channel.send(
                f"{member.mention}, configure your channel settings:", view=view
            )
        except discord.Forbidden:
            logger.warning(f"Cannot send message to '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Error sending settings view to '{channel.name}': {e}")

        try:
            await update_channel_owner(channel, member.id, owner_id)
            await send_message(
                interaction,
                f"You have claimed ownership of '{channel.name}'.",
                ephemeral=True,
            )
            logger.info(f"{member.display_name} claimed ownership of '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Failed to claim ownership: {e}")
            await send_message(
                interaction, "Failed to claim ownership of the channel.", ephemeral=True
            )

    @app_commands.command(
        name="transfer",
        description="Transfer channel ownership to another user in your voice channel.",
    )
    @app_commands.describe(new_owner="Who should be the new channel owner?")
    @app_commands.guild_only()
    async def transfer_ownership(
        self, interaction: discord.Interaction, new_owner: discord.Member
    ) -> None:
        """
        Transfers channel ownership to a specified member.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if new_owner not in channel.members:
            await send_message(
                interaction,
                "The specified user must be in your channel to transfer ownership.",
                ephemeral=True,
            )
            return

        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
                (new_owner.id, channel.id),
            )
            await db.commit()

        overwrites = channel.overwrites.copy()
        if old_overwrite := overwrites.get(interaction.user, None):
            old_overwrite.manage_channels = False
            overwrites[interaction.user] = old_overwrite

        new_ow = overwrites.get(new_owner, discord.PermissionOverwrite())
        new_ow.manage_channels = True
        new_ow.connect = True
        overwrites[new_owner] = new_ow

        try:
            await edit_channel(channel, overwrites=overwrites)
            await send_message(
                interaction,
                f"Channel ownership transferred to {new_owner.display_name}.",
                ephemeral=True,
            )
            msg = (
                f"{interaction.user.display_name} transferred ownership of "
                f"'{channel.name}' to {new_owner.display_name}."
            )
            logger.info(msg)
        except Exception as e:
            logger.exception(f"Failed to transfer ownership: {e}")
            await send_message(
                interaction, f"Failed to transfer ownership: {e}", ephemeral=True
            )

    @app_commands.command(name="help", description="Show help for voice commands.")
    @app_commands.guild_only()
    async def voice_help(self, interaction: discord.Interaction) -> None:
        """
        Displays a help embed with available voice commands.
        """
        excluded_commands = {"setup", "admin_reset", "admin_list"}
        commands_list = [
            f"**/voice {command.name}** - {command.description}"
            for command in self.walk_app_commands()
            if command.parent
            and command.parent.name == "voice"
            and command.name not in excluded_commands
        ]
        if not commands_list:
            await send_message(
                interaction, "No voice commands available.", ephemeral=True
            )
            return

        help_text = "\n".join(commands_list)
        embed = discord.Embed(
            title="🎙️ Voice Commands Help",
            description=help_text,
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text="Use these commands or the dropdown menus to manage your voice channels effectively."
        )
        await send_message(interaction, "", embed=embed, ephemeral=True)

    @app_commands.command(
        name="owner",
        description="List all voice channels managed by the bot and their owners.",
    )
    @app_commands.guild_only()
    async def voice_owner(self, interaction: discord.Interaction) -> None:
        """
        Lists all managed voice channels and their owners.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT voice_channel_id, owner_id FROM user_voice_channels"
            )
            rows = await cursor.fetchall()

        if not rows:
            await send_message(
                interaction,
                "There are no active voice channels managed by the bot.",
                ephemeral=True,
            )
            return

        message = "**Active Voice Channels Managed by the Bot:**\n"
        for channel_id, owner_id in rows:
            channel = self.bot.get_channel(channel_id)
            owner = interaction.guild.get_member(owner_id)
            if channel and owner:
                message += f"- {channel.name} (Owner: {owner.display_name})\n"
            elif channel:
                message += f"- {channel.name} (Owner: Unknown)\n"
                msg = (
                    f"Voice owner listing: channel '{channel.name}' (ID: {channel_id}) "
                    + "has no known owner; leaving DB entry for manual/admin review."
                )
                logger.info(msg)

        await send_message(interaction, message, ephemeral=True)

    # ---------------------------
    # Admin Commands
    # ---------------------------

    @app_commands.command(name="setup", description="Set up the voice channel system.")
    @app_commands.guild_only()
    @app_commands.describe(
        category="Category to place voice channels in",
        num_channels="Number of 'Join to Create' channels",
    )
    async def setup_voice(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        num_channels: int,
    ) -> None:
        """
        Sets up the voice channel system by creating the specified number of join-to-create channels.
        Only bot admins can execute this command.
        """
        member = interaction.user
        if all(r.id not in self.bot_admin_role_ids for r in member.roles):
            await send_message(
                interaction, "Only bot admins can set up the bot.", ephemeral=True
            )
            return

        if not (1 <= num_channels <= 10):
            await send_message(
                interaction,
                "Please specify a number of channels between 1 and 10.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        await send_message(interaction, "Starting setup...", ephemeral=True)

        # Store in guild_settings table
        async with Database.get_connection() as db:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
                (guild_id, "voice_category_id", str(category.id)),
            )
            await db.commit()

        # Update the in-memory maps
        self.guild_voice_categories[guild_id] = category.id
        # Also update legacy attribute for backward compatibility
        self.voice_category_id = category.id

        join_to_create_channel_ids = []
        try:
            for i in range(num_channels):
                ch_name = (
                    f"Join to Create #{i + 1}" if num_channels > 1 else "Join to Create"
                )
                voice_channel = await create_voice_channel(
                    guild=interaction.guild, name=ch_name, category=category
                )
                join_to_create_channel_ids.append(voice_channel.id)

            # Store in guild_settings table
            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
                    (
                        guild_id,
                        "join_to_create_channel_ids",
                        json.dumps(join_to_create_channel_ids),
                    ),
                )
                await db.commit()

                # Also store in legacy settings for backward compatibility
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (
                        "join_to_create_channel_ids",
                        json.dumps(join_to_create_channel_ids),
                    ),
                )
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ("voice_category_id", str(category.id)),
                )
                await db.commit()

            # Update the in-memory maps
            self.guild_jtc_channels[guild_id] = join_to_create_channel_ids
            # Also update legacy attribute for backward compatibility
            self.join_to_create_channel_ids = join_to_create_channel_ids

            await send_message(interaction, "Setup complete!", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error creating voice channels: {e}")
            await followup_send_message(
                interaction,
                "Failed to create voice channels. Check bot permissions.",
                ephemeral=True,
            )

    async def _reset_current_channel_settings(
        self, member: discord.Member, guild_id=None, jtc_channel_id=None
    ) -> None:
        """
        Resets the user's channel settings to defaults for a single guild/JTC or globally
        within a guild. This clears DB settings and attempts to reset the live channel
        properties when an active channel exists.
        """
        async with Database.get_connection() as db:
            if guild_id and jtc_channel_id:
                await db.execute(
                    "UPDATE channel_settings SET channel_name = NULL, user_limit = NULL, lock = 0 WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (member.id, guild_id, jtc_channel_id),
                )
                await db.execute(
                    "DELETE FROM channel_permissions WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (member.id, guild_id, jtc_channel_id),
                )
                await db.execute(
                    "DELETE FROM channel_ptt_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (member.id, guild_id, jtc_channel_id),
                )
                await db.execute(
                    "DELETE FROM channel_priority_speaker_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (member.id, guild_id, jtc_channel_id),
                )
                await db.execute(
                    "DELETE FROM channel_soundboard_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (member.id, guild_id, jtc_channel_id),
                )
            elif guild_id:
                await db.execute(
                    "UPDATE channel_settings SET channel_name = NULL, user_limit = NULL, lock = 0 WHERE user_id = ? AND guild_id = ?",
                    (member.id, guild_id),
                )
                await db.execute(
                    "DELETE FROM channel_permissions WHERE user_id = ? AND guild_id = ?",
                    (member.id, guild_id),
                )
                await db.execute(
                    "DELETE FROM channel_ptt_settings WHERE user_id = ? AND guild_id = ?",
                    (member.id, guild_id),
                )
                await db.execute(
                    "DELETE FROM channel_priority_speaker_settings WHERE user_id = ? AND guild_id = ?",
                    (member.id, guild_id),
                )
                await db.execute(
                    "DELETE FROM channel_soundboard_settings WHERE user_id = ? AND guild_id = ?",
                    (member.id, guild_id),
                )
            else:
                await db.execute(
                    "UPDATE channel_settings SET channel_name = NULL, user_limit = NULL, lock = 0 WHERE user_id = ?",
                    (member.id,),
                )
                await db.execute(
                    "DELETE FROM channel_permissions WHERE user_id = ?", (member.id,)
                )
                await db.execute(
                    "DELETE FROM channel_ptt_settings WHERE user_id = ?", (member.id,)
                )
                await db.execute(
                    "DELETE FROM channel_priority_speaker_settings WHERE user_id = ?",
                    (member.id,),
                )
                await db.execute(
                    "DELETE FROM channel_soundboard_settings WHERE user_id = ?",
                    (member.id,),
                )
            await db.commit()

        # Attempt to reset live voice channel properties if the user currently owns one
        channel = await get_user_channel(self.bot, member, guild_id, jtc_channel_id)
        if not channel:
            return

        # Resolve the join-to-create channel to derive defaults
        jtc_list = []
        if guild_id:
            jtc_list = self.guild_jtc_channels.get(guild_id, [])
        if not jtc_list and getattr(self, "join_to_create_channel_ids", None):
            try:
                jtc_list = [int(i) for i in self.join_to_create_channel_ids]
            except Exception:
                jtc_list = []

        if not jtc_list:
            logger.warning(
                "No join-to-create channel configured for this guild; skipping live channel property reset."
            )
            return

        join_to_create_channel = self.bot.get_channel(jtc_list[0])
        if not join_to_create_channel:
            logger.warning(
                "Join-to-create channel not found; skipping live channel property reset."
            )
            return

        default_overwrites = join_to_create_channel.overwrites
        default_user_limit = join_to_create_channel.user_limit
        default_bitrate = join_to_create_channel.bitrate

        try:
            default_name = f"{member.display_name}'s Channel"[:32]
            overwrites = default_overwrites.copy()
            overwrites[member] = discord.PermissionOverwrite(
                manage_channels=True, connect=True
            )
            await channel.edit(
                name=default_name,
                overwrites=overwrites,
                user_limit=default_user_limit,
                bitrate=default_bitrate,
            )
        except Exception as e:
            logger.exception(f"Failed to reset channel properties to defaults: {e}")

    async def _reset_all_user_settings(self, member: discord.Member) -> None:
        """Remove all voice-related settings for a user across all guilds and delete
        any active channels owned by them where possible.

        This is destructive and intended for admin use only.
        """
        async with Database.get_connection() as db:
            # Gather owned channel IDs before deleting rows
            cursor = await db.execute(
                "SELECT voice_channel_id FROM user_voice_channels WHERE owner_id = ?",
                (member.id,),
            )
            rows = await cursor.fetchall()
            channel_ids = [r[0] for r in rows]

            # Clear settings across all guilds
            await db.execute(
                "UPDATE channel_settings SET channel_name = NULL, user_limit = NULL, lock = 0 WHERE user_id = ?",
                (member.id,),
            )
            await db.execute(
                "DELETE FROM channel_permissions WHERE user_id = ?", (member.id,)
            )
            await db.execute(
                "DELETE FROM channel_ptt_settings WHERE user_id = ?", (member.id,)
            )
            await db.execute(
                "DELETE FROM channel_priority_speaker_settings WHERE user_id = ?",
                (member.id,),
            )
            await db.execute(
                "DELETE FROM channel_soundboard_settings WHERE user_id = ?",
                (member.id,),
            )
            await db.execute(
                "DELETE FROM voice_cooldowns WHERE user_id = ?", (member.id,)
            )
            await db.execute(
                "DELETE FROM user_voice_channels WHERE owner_id = ?", (member.id,)
            )
            await db.commit()

        # Attempt to delete the actual Discord channels where possible
        for cid in channel_ids:
            try:
                ch = self.bot.get_channel(cid)
                if ch is None:
                    try:
                        ch = await self.bot.fetch_channel(cid)
                    except Exception:
                        ch = None
                if ch is not None:
                    try:
                        await delete_channel(ch)
                        self.managed_voice_channels.discard(cid)
                        logger.info(
                            f"Deleted channel '{getattr(ch, 'name', cid)}' for user {member.display_name} during global reset."
                        )
                    except Exception:
                        logger.exception(
                            f"Failed to delete channel {cid} during global reset."
                        )
            except Exception:
                logger.exception(
                    f"Error while attempting to remove channel {cid} during global reset."
                )
        logger.info(f"Reset settings for {member.display_name}'s channel.")

    def is_bot_admin_or_lead_moderator(self, member: discord.Member) -> bool:
        """
        Checks if a member is a bot admin or a lead moderator.
        """
        roles = [r.id for r in member.roles]
        return any(
            r_id in roles
            for r_id in (self.bot_admin_role_ids + self.lead_moderator_role_ids)
        )

    @app_commands.command(
        name="admin_reset", description="Admin command to reset a user's voice channel."
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user whose voice channel settings you want to reset.",
        jtc_channel="Specific join-to-create channel to reset settings for (optional).",
        global_reset="If true, reset this user's settings across all guilds and channels (destructive).",
    )
    async def admin_reset_voice(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        jtc_channel: discord.VoiceChannel | None = None,
        global_reset: bool = False,
    ) -> None:
        """
        Allows bot admins or lead moderators to reset a user's voice channel.

        Args:
            interaction: The interaction context
            user: The user whose settings to reset
            jtc_channel: Optional specific join-to-create channel to reset
        """
        if not self.is_bot_admin_or_lead_moderator(interaction.user):
            await send_message(
                interaction,
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        jtc_channel_id = jtc_channel.id if jtc_channel else None

        # If a specific JTC channel was provided, validate it's a JTC channel
        if jtc_channel:
            join_to_create_channels = self.guild_jtc_channels.get(guild_id, [])
            if not join_to_create_channels:
                # Try legacy fallback
                join_to_create_channels = [
                    int(id) for id in self.join_to_create_channel_ids
                ]

            if jtc_channel.id not in join_to_create_channels:
                await send_message(
                    interaction,
                    f"The channel {jtc_channel.mention} is not a join-to-create channel.",
                    ephemeral=True,
                )
                return

        # If global_reset requested, reject combination with a specific jtc_channel
        if global_reset and jtc_channel is not None:
            await send_message(
                interaction,
                "Cannot specify a specific JTC channel when performing a global reset. Use either a channel or global_reset.",
                ephemeral=True,
            )
            return

        # If global reset requested, perform across all guilds and channels
        if global_reset:
            await send_message(
                interaction, "Starting global reset for user...", ephemeral=True
            )
            await self._reset_all_user_settings(user)
            await send_message(
                interaction,
                f"All voice channel settings and channels for {user.display_name} have been reset across all guilds.",
                ephemeral=True,
            )
            logger.info(
                f"{interaction.user.display_name} performed global reset for {user.display_name}."
            )
            return

        # If no JTC channel was specified but user has an active channel, get its JTC channel
        if not jtc_channel_id:
            active_channel = await get_user_channel(self.bot, user, guild_id)
            if active_channel:
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT jtc_channel_id FROM user_voice_channels WHERE voice_channel_id = ? AND guild_id = ?",
                        (active_channel.id, guild_id),
                    )
                    if row := await cursor.fetchone():
                        jtc_channel_id = row[0]

        # Reset settings with guild context
        await self._reset_current_channel_settings(user, guild_id, jtc_channel_id)

        # If user has an active channel, delete it
        active_channel = await get_user_channel(
            self.bot, user, guild_id, jtc_channel_id
        )
        if active_channel:
            try:
                await delete_channel(active_channel)
                self.managed_voice_channels.discard(active_channel.id)
                logger.info(
                    f"Deleted {user.display_name}'s active voice channel as part of admin reset."
                )
            except discord.NotFound:
                logger.warning(
                    f"Channel '{active_channel.id}' not found. It may have already been deleted."
                )

        # Build success message
        if jtc_channel:
            success_message = f"{user.display_name}'s voice channel settings for {jtc_channel.name} have been reset."
        else:
            success_message = f"{user.display_name}'s voice channel settings for this server have been reset."

        await send_message(
            interaction,
            success_message,
            ephemeral=True,
        )
        logger.info(
            f"{interaction.user.display_name} reset {user.display_name}'s voice channel settings."
        )

    @app_commands.command(
        name="admin_list",
        description="View saved permissions and settings for a user's voice channel (Admins/Moderators only).",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user whose voice channel settings you want to view."
    )
    async def admin_list_channel(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        """
        Allows an admin to view saved channel settings and permissions for a specific user.
        """
        admin_role_ids = self.bot_admin_role_ids + self.lead_moderator_role_ids
        user_roles = [role.id for role in interaction.user.roles]
        if all(role_id not in user_roles for role_id in admin_role_ids):
            await send_message(
                interaction,
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        # Get the current guild ID
        guild_id = interaction.guild.id

        # Find all join-to-create channels in this guild
        join_to_create_channels = self.guild_jtc_channels.get(guild_id, [])
        if not join_to_create_channels:
            # Try legacy fallback
            join_to_create_channels = [
                int(id) for id in self.join_to_create_channel_ids
            ]

        # Query for all user's channel settings in this guild
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT guild_id, jtc_channel_id, channel_name, user_limit, lock FROM channel_settings WHERE user_id = ? AND guild_id = ?",
                (user.id, guild_id),
            )
            rows = await cursor.fetchall()

        if not rows:
            await send_message(
                interaction,
                f"{user.display_name} does not have saved channel settings in this server.",
                ephemeral=True,
            )
            return

        class FakeInteraction:
            def __init__(self, user, guild) -> None:
                self.user = user
                self.guild = guild

        fake_inter = FakeInteraction(user, interaction.guild)

        # For each channel setting, create and send an embed
        for row in rows:
            guild_id, jtc_channel_id = row[0], row[1]

            # Get the JTC channel name
            jtc_channel = interaction.guild.get_channel(jtc_channel_id)
            jtc_name = (
                f"JTC Channel: {jtc_channel.name}"
                if jtc_channel
                else f"JTC Channel ID: {jtc_channel_id}"
            )

            # Fetch settings for this specific JTC channel
            settings = await fetch_channel_settings(
                self.bot,
                fake_inter,
                allow_inactive=True,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )

            if settings:
                formatted = format_channel_settings(settings, interaction)
                embed = create_voice_settings_embed(
                    settings=settings,
                    formatted=formatted,
                    title=f"Saved Channel Settings for {user.display_name}",
                    footer=f"{jtc_name} | Use /voice admin_reset to reset this user's channel.",
                )
                await send_message(interaction, "", embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Voice(bot))
    logger.info("Voice cog loaded.")
