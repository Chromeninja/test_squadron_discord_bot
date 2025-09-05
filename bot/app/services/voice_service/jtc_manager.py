# bot/app/services/voice_service/jtc_manager.py
"""
Service for managing join-to-create voice channel operations.

This service handles:
- Channel creation and destruction
- User movement between channels
- Permission inheritance
"""

from typing import Optional, Dict, Any, Set, List
import discord
from helpers.logger import get_logger
from helpers.voice_utils import get_user_channel, update_channel_settings, get_user_game_name
from helpers.voice_repo import get_user_channel_id
from helpers.voice_permissions import assert_base_permissions
from helpers.database import Database

logger = get_logger(__name__)


class JoinToCreateManager:
    """
    Service for managing join-to-create voice channel lifecycle.
    
    Centralizes:
    - Channel creation logic
    - Permission setup
    - Cleanup operations
    """

    def __init__(self, discord_gateway, app_config):
        """Initialize the JTC manager with Discord gateway and config."""
        self.discord_gateway = discord_gateway
        self.app_config = app_config
        self.managed_channels: Set[int] = set()
        self.guild_jtc_channels: Dict[int, List[int]] = {}
        logger.debug("JoinToCreateManager initialized")

    def is_jtc_channel(self, channel_id: int, guild_id: int) -> bool:
        """
        Check if a channel is a join-to-create channel.
        
        Args:
            channel_id: Channel ID to check
            guild_id: Guild ID
            
        Returns:
            True if channel is a JTC channel
        """
        jtc_channels = self.app_config.voice.join_to_create_channels.get(str(guild_id), [])
        return channel_id in jtc_channels

    async def handle_jtc_join(self, member: discord.Member, jtc_channel: discord.VoiceChannel) -> Optional[discord.VoiceChannel]:
        """
        Handle a member joining a join-to-create channel.
        
        Args:
            member: Member who joined
            jtc_channel: The JTC channel they joined
            
        Returns:
            The created voice channel, if successful
        """
        try:
            # Check if user already has a channel
            existing_channel = await get_user_channel(self.discord_gateway.bot, member, member.guild.id, jtc_channel.id)
            if existing_channel:
                # Move to existing channel
                await self.discord_gateway.move_member(member, existing_channel)
                logger.debug(f"Moved user {member.id} to existing channel {existing_channel.id}")
                return existing_channel
                
            # Create new channel
            game_name = get_user_game_name(member)
            if game_name:
                channel_name = f"{member.display_name}'s {game_name}"
            else:
                channel_name = f"{member.display_name}'s Channel"
                
            # Create in same category as JTC channel
            category = jtc_channel.category
            new_channel = await self.create_temporary_channel(
                member.guild, member, category, channel_name, jtc_channel.id
            )
            
            if new_channel:
                # Move user to the new channel
                await self.discord_gateway.move_member(member, new_channel)
                self.add_managed_channel(new_channel.id)
                logger.info(f"Created and moved user {member.id} to new channel {new_channel.id}")
                
            return new_channel
            
        except Exception as e:
            logger.exception(f"Error handling JTC join for user {member.id}: {e}")
            return None

    async def create_temporary_channel(self, guild: discord.Guild, owner: discord.Member, category: discord.CategoryChannel, name: str, jtc_channel_id: int) -> Optional[discord.VoiceChannel]:
        """
        Create a temporary voice channel for the user.
        
        Args:
            guild: Discord guild
            owner: Channel owner
            category: Category to create channel in
            name: Channel name
            jtc_channel_id: The JTC channel ID this was created from
            
        Returns:
            Created voice channel or None if failed
        """
        try:
            # Create the channel
            channel = await self.discord_gateway.create_voice_channel(
                guild, name, category=category
            )
            
            if not channel:
                logger.error(f"Failed to create voice channel '{name}'")
                return None
                
            # Set up base permissions
            bot_member = guild.me
            default_role = guild.default_role
            await assert_base_permissions(channel, bot_member, owner, default_role)
            
            # Record the channel in database
            async with Database.get_connection() as db:
                await db.execute(
                    """
                    INSERT INTO user_voice_channels (owner_id, voice_channel_id, guild_id, jtc_channel_id, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    """,
                    (owner.id, channel.id, guild.id, jtc_channel_id)
                )
                await db.commit()
                
            logger.info(f"Created temporary channel {channel.id} for user {owner.id}")
            return channel
            
        except Exception as e:
            logger.exception(f"Error creating temporary channel for user {owner.id}: {e}")
            return None

    async def cleanup_empty_channel(self, channel_id: int) -> bool:
        """
        Clean up an empty managed voice channel.
        
        Args:
            channel_id: Channel ID to clean up
            
        Returns:
            True if channel was cleaned up
        """
        try:
            channel = self.discord_gateway.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                # Channel doesn't exist, remove from managed set and database
                self.remove_managed_channel(channel_id)
                await self._remove_channel_from_database(channel_id)
                return True
                
            # Check if channel is empty
            if len(channel.members) > 0:
                logger.debug(f"Channel {channel_id} not empty, skipping cleanup")
                return False
                
            # Delete the channel
            await self.discord_gateway.delete_channel(channel)
            self.remove_managed_channel(channel_id)
            await self._remove_channel_from_database(channel_id)
            
            logger.info(f"Cleaned up empty channel {channel_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error cleaning up channel {channel_id}: {e}")
            return False

    async def _remove_channel_from_database(self, channel_id: int) -> None:
        """Remove channel record from database."""
        try:
            async with Database.get_connection() as db:
                await db.execute(
                    "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                    (channel_id,)
                )
                await db.commit()
        except Exception as e:
            logger.exception(f"Error removing channel {channel_id} from database: {e}")

    def add_managed_channel(self, channel_id: int) -> None:
        """Add a channel to the managed channels set."""
        self.managed_channels.add(channel_id)

    def remove_managed_channel(self, channel_id: int) -> None:
        """Remove a channel from the managed channels set."""
        self.managed_channels.discard(channel_id)

    def is_managed_channel(self, channel_id: int) -> bool:
        """Check if a channel is managed by this service."""
        return channel_id in self.managed_channels

    async def cleanup_stale_channels(self, guild_id: int) -> int:
        """
        Clean up stale voice channels that no longer exist on Discord.
        
        Args:
            guild_id: Guild ID to clean up
            
        Returns:
            Number of stale records removed
        """
        try:
            guild = self.discord_gateway.bot.get_guild(guild_id)
            if not guild:
                return 0
                
            removed_count = 0
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT voice_channel_id FROM user_voice_channels WHERE guild_id = ?",
                    (guild_id,)
                )
                channel_ids = [row[0] for row in await cursor.fetchall()]
                
                for channel_id in channel_ids:
                    channel = guild.get_channel(channel_id)
                    if not channel:
                        # Channel doesn't exist, remove from database
                        await db.execute(
                            "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                            (channel_id,)
                        )
                        self.remove_managed_channel(channel_id)
                        removed_count += 1
                        logger.debug(f"Removed stale channel record {channel_id}")
                        
                await db.commit()
                
            return removed_count
            
        except Exception as e:
            logger.exception(f"Error cleaning up stale channels in guild {guild_id}: {e}")
            return 0

    def load_jtc_channels_from_config(self) -> None:
        """Load JTC channel configuration from app config."""
        try:
            self.guild_jtc_channels = self.app_config.voice.join_to_create_channels.copy()
            logger.debug(f"Loaded JTC channels: {self.guild_jtc_channels}")
        except Exception as e:
            logger.exception(f"Error loading JTC channels from config: {e}")
