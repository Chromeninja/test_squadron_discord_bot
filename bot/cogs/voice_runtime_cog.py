# bot/cogs/voice_runtime_cog.py
"""
Voice Runtime Cog

This cog handles runtime voice functionality including:
  - Voice state change listeners
  - Channel creation and deletion
  - Background cleanup tasks
  - Channel reconciliation
"""

import asyncio
import json
import time

import discord
from discord.ext import commands, tasks

from config.config_loader import ConfigLoader
from helpers.database import Database
from helpers.discord_api import (
    create_voice_channel,
    delete_channel,
    move_member,
)
from helpers.logger import get_logger
from helpers.voice_utils import (
    get_user_channel,
    get_user_game_name,
)
from helpers.voice_repo import (
    get_stale_voice_entries,
    cleanup_user_voice_data,
    cleanup_legacy_user_voice_data,
)
from bot.app.services.voice_service import JoinToCreateManager, VoiceSettingsService

logger = get_logger(__name__)


class VoiceRuntimeCog(commands.Cog):
    """
    Cog for managing dynamic voice channel runtime operations.
    Handles events, background tasks, and channel lifecycle management.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.cooldown_seconds = self.config["voice"].get("cooldown_seconds", 60)
        self.expiry_days = self.config["voice"].get("expiry_days", 30)
        
        # Initialize voice services (will be injected by bot)
        self.jtc_manager: JoinToCreateManager = None
        self.settings_service: VoiceSettingsService = None
        
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

    def inject_voice_services(self, jtc_manager: JoinToCreateManager, settings_service: VoiceSettingsService):
        """Inject voice services after cog initialization."""
        self.jtc_manager = jtc_manager
        self.settings_service = settings_service
        logger.debug("Voice services injected into runtime cog")

    async def cog_load(self):
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
                ("voice_category_id",)
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
                        self.guild_jtc_channels[first_guild_id] = self.join_to_create_channel_ids

            if not self.guild_voice_categories:
                cursor = await db.execute(
                    "SELECT value FROM settings WHERE key = ?", ("voice_category_id",)
                )
                if row := await cursor.fetchone():
                    self.voice_category_id = int(row[0])
                    # For legacy compatibility, add to first guild
                    if self.bot.guilds and self.voice_category_id:
                        first_guild_id = self.bot.guilds[0].id
                        self.guild_voice_categories[first_guild_id] = self.voice_category_id
                        
        # Reconcile managed channels on startup (non-blocking)
        # Use the central reconciliation routine which will inspect stored
        # channels, keep those with members, delete empty channels, and
        # remove DB rows for missing channels.
        self.bot.loop.create_task(self.reconcile_managed_channels())
        # Start periodic cleanup loop for stale voice channel data.
        self.bot.loop.create_task(self.channel_data_cleanup_loop())
        logger.info(
            "Voice cog loaded; scheduled reconciliation of managed voice channels."
        )

    async def reconcile_managed_channels(self):
        """
        Reconcile managed voice channels on startup.
        Check which channels still exist, have members, and clean up as needed.
        """
        try:
            # Get all stored channel IDs from the database
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT voice_channel_id FROM user_voice_channels"
                )
                stored_channels = await cursor.fetchall()

            kept_count = 0
            removed_empty_count = 0
            missing_cleaned_count = 0

            for (channel_id,) in stored_channels:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    # Channel doesn't exist, clean up database entry
                    await cleanup_user_voice_data(None, None, channel_id)
                    missing_cleaned_count += 1
                    logger.debug(f"Cleaned up missing channel {channel_id} from database")
                    continue

                if len(channel.members) == 0:
                    # Empty channel, delete it
                    try:
                        await delete_channel(channel)
                        removed_empty_count += 1
                        logger.debug(f"Deleted empty channel {channel.name} ({channel_id})")
                    except discord.NotFound:
                        # Channel was already deleted
                        await cleanup_user_voice_data(None, None, channel_id)
                        missing_cleaned_count += 1
                    except Exception as e:
                        logger.error(f"Error deleting empty channel {channel_id}: {e}")
                        # Keep in managed list for now
                        self.managed_voice_channels.add(channel_id)
                        kept_count += 1
                else:
                    # Channel has members, keep it
                    self.managed_voice_channels.add(channel_id)
                    kept_count += 1
                    logger.debug(f"Keeping channel {channel.name} ({channel_id}) with {len(channel.members)} members")

            logger.info(
                f"Voice reconcile summary: kept={kept_count}, removed_empty={removed_empty_count}, missing_cleaned={missing_cleaned_count}"
            )
        except Exception as e:
            logger.error(f"Error during channel reconciliation: {e}")

    async def cleanup_voice_channel(self, channel_id):
        """
        Remove a voice channel from the database and from the managed list.
        """
        try:
            await cleanup_user_voice_data(None, None, channel_id)
            self.managed_voice_channels.discard(channel_id)
            logger.debug(f"Cleaned up voice channel data for channel {channel_id}")
        except Exception as e:
            logger.error(f"Error cleaning up voice channel {channel_id}: {e}")

    async def reconcile_voice_channel(self, channel_id: int):
        """
        Reconcile a specific voice channel.
        Check if it exists and has members, clean up if necessary.
        """
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            # Channel doesn't exist, clean up database entry
            await self.cleanup_voice_channel(channel_id)
            logger.debug(f"Reconciled missing channel {channel_id}")
            return

        if len(channel.members) == 0:
            # Empty channel, delete it
            try:
                await delete_channel(channel)
                logger.debug(f"Reconciled and deleted empty channel {channel.name} ({channel_id})")
            except discord.NotFound:
                # Channel was already deleted
                await self.cleanup_voice_channel(channel_id)
            except Exception as e:
                logger.error(f"Error reconciling channel {channel_id}: {e}")
        else:
            # Channel has members, ensure it's in managed list
            self.managed_voice_channels.add(channel_id)
            logger.debug(f"Reconciled channel {channel.name} ({channel_id}) with {len(channel.members)} members")

    async def _schedule_service_cleanup(self, channel_id: int, delay: int = 30):
        """
        Schedule cleanup of a channel using the JTC service.
        """
        await asyncio.sleep(delay)
        if self.jtc_manager:
            if await self.jtc_manager.cleanup_empty_channel(channel_id):
                self.managed_voice_channels.discard(channel_id)
                logger.debug(f"Service cleaned up empty channel {channel_id} after {delay}s delay")

    async def _schedule_deletion_if_still_empty(self, channel_id: int, delay: int = 30):
        """
        Schedule deletion of a channel if it's still empty after a delay.
        """
        await asyncio.sleep(delay)
        channel = self.bot.get_channel(channel_id)
        if channel and len(channel.members) == 0:
            try:
                await delete_channel(channel)
                await self.cleanup_voice_channel(channel_id)
                logger.debug(f"Deleted empty channel {channel.name} after {delay}s delay")
            except discord.NotFound:
                await self.cleanup_voice_channel(channel_id)
            except Exception as e:
                logger.error(f"Error during scheduled cleanup of channel ID {channel.id}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
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
        guild_id = member.guild.id
        if guild_id not in self._voice_event_locks:
            self._voice_event_locks[guild_id] = asyncio.Lock()

        async with self._voice_event_locks[guild_id]:
            await self._handle_voice_state_update_locked(member, before, after)

    async def _handle_voice_state_update_locked(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle voice state update with guild-level locking."""
        guild_id = member.guild.id
        
        # Get JTC channels for this guild
        join_to_create_channels = self.guild_jtc_channels.get(guild_id, [])
        if not join_to_create_channels:
            # Try legacy fallback
            join_to_create_channels = [int(id) for id in self.join_to_create_channel_ids]

        # Handle leaving a managed channel
        if (
            before.channel
            and before.channel.id in self.managed_voice_channels
            and len(before.channel.members) == 0
        ):
            # Channel is now empty, schedule deletion
            logger.debug(f"Scheduling deletion of empty channel {before.channel.name}")
            if self.jtc_manager and self.jtc_manager.is_managed_channel(before.channel.id):
                # Use service to cleanup
                self.bot.loop.create_task(
                    self._schedule_service_cleanup(before.channel.id)
                )
            else:
                # Fallback to legacy cleanup
                self.bot.loop.create_task(
                    self._schedule_deletion_if_still_empty(before.channel.id)
                )

        # Handle joining a Join-to-Create channel
        if after.channel and after.channel.id in join_to_create_channels:
            if self.jtc_manager:
                # Use the service to handle JTC join
                await self.jtc_manager.handle_jtc_join(member, after.channel)
                # Update managed channels set
                if after.channel.id not in self.managed_voice_channels:
                    user_channel = await get_user_channel(self.bot, member, guild_id, after.channel.id)
                    if user_channel:
                        self.managed_voice_channels.add(user_channel.id)
            else:
                # Fallback to legacy method
                await self._handle_jtc_join(member, after.channel)

    async def _handle_jtc_join(self, member: discord.Member, jtc_channel: discord.VoiceChannel):
        """Handle a member joining a join-to-create channel."""
        guild_id = member.guild.id
        
        # Check if user already has a channel for this JTC
        existing_channel = await get_user_channel(self.bot, member, guild_id, jtc_channel.id)
        if existing_channel:
            try:
                await move_member(member, existing_channel)
                logger.debug(f"Moved {member.display_name} to existing channel {existing_channel.name}")
                return
            except Exception as e:
                logger.error(f"Error moving member to existing channel: {e}")

        # Create new channel
        await self._create_user_voice_channel(member, jtc_channel)

    async def _create_user_voice_channel(self, member: discord.Member, jtc_channel: discord.VoiceChannel):
        """Create a new voice channel for a user."""
        guild_id = member.guild.id
        
        # Get voice category for this guild
        voice_category_id = self.guild_voice_categories.get(guild_id)
        if not voice_category_id:
            voice_category_id = self.voice_category_id  # Legacy fallback
            
        category = self.bot.get_channel(voice_category_id) if voice_category_id else None
        
        # Generate channel name
        game_name = await get_user_game_name(member)
        if game_name:
            channel_name = f"{member.display_name}: {game_name}"[:32]
        else:
            channel_name = f"{member.display_name}'s Channel"[:32]

        try:
            # Create the channel
            new_channel = await create_voice_channel(
                member.guild,
                channel_name,
                category=category,
                user_limit=0,
                reason=f"Voice channel created for {member.display_name}"
            )
            
            # Add to managed channels
            self.managed_voice_channels.add(new_channel.id)
            
            # Store in database
            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO user_voice_channels (user_id, voice_channel_id, owner_id, guild_id, jtc_channel_id) VALUES (?, ?, ?, ?, ?)",
                    (member.id, new_channel.id, member.id, guild_id, jtc_channel.id),
                )
                await db.commit()
            
            # Move user to new channel
            await move_member(member, new_channel)
            
            # Apply stored settings (stub for now)
            await self._apply_channel_settings(new_channel, member, jtc_channel.id)
            
            logger.info(f"Created voice channel {new_channel.name} for {member.display_name}")
            
        except Exception as e:
            logger.error(f"Error creating voice channel for {member.display_name}: {e}")

    async def _apply_channel_settings(self, channel: discord.VoiceChannel, owner: discord.Member, jtc_channel_id: int):
        """Apply stored settings to a newly created channel."""
        if self.settings_service:
            # Use the settings service to apply stored settings
            try:
                # This would apply all stored settings for the user
                await self.settings_service.enforce_channel_permissions(
                    channel, owner.id, owner.guild.id, jtc_channel_id
                )
                logger.debug(f"Applied settings to channel {channel.name} via service")
            except Exception as e:
                logger.error(f"Error applying settings via service: {e}")
        else:
            # Legacy stub
            logger.debug(f"Applying settings to channel {channel.name} (legacy stub)")
            pass

    @tasks.loop(hours=24)
    async def channel_data_cleanup_loop(self):
        """
        Background task to clean up stale voice channel data.
        Runs every 24 hours.
        """
        try:
            await self.cleanup_stale_channel_data()
        except Exception as e:
            logger.error(f"Error in channel data cleanup loop: {e}")

    async def cleanup_stale_channel_data(self):
        """
        Clean up stale voice channel data from the database.
        """
        cutoff_timestamp = int(time.time()) - (self.expiry_days * 24 * 60 * 60)
        logger.info(f"Running stale channel data cleanup (cutoff={cutoff_timestamp}).")

        try:
            # Get stale entries
            stale_entries = await get_stale_voice_entries(cutoff_timestamp)
            
            if not stale_entries:
                logger.info("No stale voice channel data found.")
                return

            # Determine cleanup strategy
            guild_scoped = len(set(entry[2] for entry in stale_entries if entry[2])) > 0
            
            if guild_scoped:
                logger.info("Using scoped cleanup (guild_id, jtc_channel_id, user_id)")
                for user_id, jtc_channel_id, guild_id, last_used in stale_entries:
                    await cleanup_user_voice_data(user_id, jtc_channel_id, None, guild_id)
            else:
                logger.info("Using legacy cleanup (user_id, jtc_channel_id)")
                for user_id, jtc_channel_id, guild_id, last_used in stale_entries:
                    await cleanup_legacy_user_voice_data(user_id, jtc_channel_id)

            logger.info(f"Cleaned up {len(stale_entries)} stale voice channel entries.")
            
        except Exception as e:
            logger.error(f"Error during stale channel data cleanup: {e}")

    async def _wait_for_channel_empty(self, channel: discord.VoiceChannel):
        """
        Wait for a voice channel to become empty.
        Used for cleanup operations.
        """
        try:
            while len(channel.members) > 0:
                await asyncio.sleep(5)
            logger.debug(f"Channel {channel.name} is now empty")
        except Exception as e:
            logger.error(f"Error waiting for channel {channel.id} to empty: {e}")


async def setup(bot: commands.Bot):
    """Setup function to add the VoiceRuntimeCog."""
    await bot.add_cog(VoiceRuntimeCog(bot))
    logger.info("Voice runtime cog loaded.")
