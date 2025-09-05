# bot/app/services/voice_service/settings_service.py
"""
Service for managing voice channel settings and permissions.

This service handles:
- Channel settings persistence 
- Permission management
- Settings application to channels
"""

from typing import Dict, Any, Optional, List, Tuple
import discord
from helpers.logger import get_logger
from helpers.voice_utils import (
    fetch_channel_settings, 
    update_channel_settings,
    set_voice_feature_setting,
    apply_voice_feature_toggle,
    format_channel_settings,
    create_voice_settings_embed
)
from helpers.voice_repo import upsert_channel_settings, list_permissions
from helpers.voice_permissions import enforce_permission_changes
from helpers.database import Database

logger = get_logger(__name__)


class VoiceSettingsService:
    """
    Service for managing voice channel settings and permissions.
    
    Centralizes:
    - Settings CRUD operations
    - Permission calculations
    - Settings validation
    """

    def __init__(self, discord_gateway, app_config):
        """Initialize the voice settings service."""
        self.discord_gateway = discord_gateway
        self.app_config = app_config
        logger.debug("VoiceSettingsService initialized")

    async def get_channel_settings(self, bot, interaction, guild_id: int, user_id: int, jtc_channel_id: Optional[int] = None, allow_inactive: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get voice channel settings for a user.
        
        Args:
            bot: Bot instance
            interaction: Discord interaction
            guild_id: Guild ID
            user_id: User ID
            jtc_channel_id: Optional JTC channel ID
            allow_inactive: Whether to return settings even if user has no active channel
            
        Returns:
            Dictionary of channel settings or None if not found
        """
        try:
            return await fetch_channel_settings(
                bot, interaction, allow_inactive, guild_id, jtc_channel_id
            )
        except Exception as e:
            logger.exception(f"Error getting channel settings for user {user_id}: {e}")
            return None

    async def update_basic_settings(self, user_id: int, guild_id: int, jtc_channel_id: int, **settings) -> bool:
        """
        Update basic channel settings (name, limit, lock).
        
        Args:
            user_id: User ID
            guild_id: Guild ID
            jtc_channel_id: JTC channel ID
            **settings: Settings to update (channel_name, user_limit, lock)
            
        Returns:
            True if successful
        """
        try:
            await upsert_channel_settings(user_id, guild_id, jtc_channel_id, **settings)
            logger.debug(f"Updated basic settings for user {user_id}: {settings}")
            return True
        except Exception as e:
            logger.exception(f"Error updating basic settings for user {user_id}: {e}")
            return False

    async def set_feature_permission(self, feature: str, user_id: int, target_id: int, target_type: str, enable: bool, guild_id: int, jtc_channel_id: int) -> bool:
        """
        Set a voice feature permission (PTT, priority speaker, soundboard).
        
        Args:
            feature: Feature name ("ptt", "priority_speaker", "soundboard")
            user_id: Channel owner ID
            target_id: Target user/role ID
            target_type: Target type ("user", "role", "everyone")
            enable: Whether to enable the feature
            guild_id: Guild ID
            jtc_channel_id: JTC channel ID
            
        Returns:
            True if successful
        """
        try:
            await set_voice_feature_setting(
                feature, user_id, target_id, target_type, enable, guild_id, jtc_channel_id
            )
            logger.debug(f"Set {feature} permission for user {user_id}, target {target_id}: {enable}")
            return True
        except Exception as e:
            logger.exception(f"Error setting {feature} permission: {e}")
            return False

    async def apply_settings_to_channel(self, channel: discord.VoiceChannel, settings: Dict[str, Any]) -> bool:
        """
        Apply settings to a voice channel.
        
        Args:
            channel: Voice channel to configure
            settings: Settings to apply
            
        Returns:
            True if successful
        """
        try:
            # Apply basic channel settings
            edit_kwargs = {}
            if "channel_name" in settings and settings["channel_name"]:
                edit_kwargs["name"] = settings["channel_name"]
            if "user_limit" in settings:
                edit_kwargs["user_limit"] = settings["user_limit"] or 0
                
            if edit_kwargs:
                await self.discord_gateway.edit_channel(channel, **edit_kwargs)
                
            # Apply lock/unlock if specified
            if "lock" in settings:
                await self._apply_lock_setting(channel, settings["lock"])
                
            logger.debug(f"Applied settings to channel {channel.id}")
            return True
        except Exception as e:
            logger.exception(f"Error applying settings to channel {channel.id}: {e}")
            return False

    async def _apply_lock_setting(self, channel: discord.VoiceChannel, locked: bool) -> None:
        """Apply lock/unlock setting to a channel."""
        try:
            overwrites = channel.overwrites.copy()
            default_role = channel.guild.default_role
            
            # Get or create overwrite for default role
            overwrite = overwrites.get(default_role, discord.PermissionOverwrite())
            overwrite.connect = not locked  # Lock = deny connect
            overwrites[default_role] = overwrite
            
            # Ensure owner can still connect
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                    (channel.id,)
                )
                row = await cursor.fetchone()
                if row:
                    owner_id = row[0]
                    owner = channel.guild.get_member(owner_id)
                    if owner:
                        owner_overwrite = overwrites.get(owner, discord.PermissionOverwrite())
                        owner_overwrite.connect = True
                        owner_overwrite.manage_channels = True
                        overwrites[owner] = owner_overwrite
                        
            await self.discord_gateway.edit_channel(channel, overwrites=overwrites)
        except Exception as e:
            logger.exception(f"Error applying lock setting to channel {channel.id}: {e}")

    async def apply_feature_to_channel(self, channel: discord.VoiceChannel, feature: str, target_member: discord.Member, enable: bool) -> bool:
        """
        Apply a voice feature toggle to a channel.
        
        Args:
            channel: Voice channel
            feature: Feature name
            target_member: Target member or role
            enable: Whether to enable the feature
            
        Returns:
            True if successful
        """
        try:
            await apply_voice_feature_toggle(channel, feature, target_member, enable)
            return True
        except Exception as e:
            logger.exception(f"Error applying {feature} to channel {channel.id}: {e}")
            return False

    async def reset_user_settings(self, user_id: int, guild_id: int, jtc_channel_id: int) -> bool:
        """
        Reset voice channel settings for a user.
        
        Args:
            user_id: User ID
            guild_id: Guild ID
            jtc_channel_id: JTC channel ID
            
        Returns:
            True if successful
        """
        try:
            async with Database.get_connection() as db:
                # Reset basic settings
                await db.execute(
                    "DELETE FROM channel_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (user_id, guild_id, jtc_channel_id)
                )
                
                # Reset permissions
                await db.execute(
                    "DELETE FROM channel_permissions WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (user_id, guild_id, jtc_channel_id)
                )
                
                # Reset PTT settings
                await db.execute(
                    "DELETE FROM channel_ptt_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (user_id, guild_id, jtc_channel_id)
                )
                
                # Reset priority speaker settings
                await db.execute(
                    "DELETE FROM channel_priority_speaker_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (user_id, guild_id, jtc_channel_id)
                )
                
                # Reset soundboard settings
                await db.execute(
                    "DELETE FROM channel_soundboard_settings WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                    (user_id, guild_id, jtc_channel_id)
                )
                
                await db.commit()
                
            logger.info(f"Reset all settings for user {user_id} in guild {guild_id}")
            return True
        except Exception as e:
            logger.exception(f"Error resetting settings for user {user_id}: {e}")
            return False

    async def format_settings_for_display(self, settings: Dict[str, Any], interaction) -> Dict[str, List[str]]:
        """
        Format channel settings for display in embeds.
        
        Args:
            settings: Settings dictionary
            interaction: Discord interaction for context
            
        Returns:
            Formatted settings for display
        """
        try:
            return format_channel_settings(settings, interaction)
        except Exception as e:
            logger.exception(f"Error formatting settings for display: {e}")
            return {
                "permission_lines": ["Error formatting permissions"],
                "ptt_lines": ["Error formatting PTT settings"],
                "priority_lines": ["Error formatting priority speaker"],
                "soundboard_lines": ["Error formatting soundboard settings"]
            }

    def create_settings_embed(self, settings: Dict[str, Any], formatted: Dict[str, List[str]], title: str, footer: str) -> discord.Embed:
        """
        Create a Discord embed for settings display.
        
        Args:
            settings: Settings dictionary
            formatted: Formatted settings
            title: Embed title
            footer: Embed footer
            
        Returns:
            Discord embed
        """
        try:
            return create_voice_settings_embed(settings, formatted, title, footer)
        except Exception as e:
            logger.exception(f"Error creating settings embed: {e}")
            embed = discord.Embed(title="Error", color=discord.Color.red())
            embed.description = "Failed to create settings display"
            return embed

    async def enforce_channel_permissions(self, channel: discord.VoiceChannel, user_id: int, guild_id: int, jtc_channel_id: int) -> bool:
        """
        Enforce all permission changes for a channel.
        
        Args:
            channel: Voice channel
            user_id: Owner user ID
            guild_id: Guild ID
            jtc_channel_id: JTC channel ID
            
        Returns:
            True if successful
        """
        try:
            await enforce_permission_changes(channel, self.discord_gateway.bot, user_id, guild_id, jtc_channel_id)
            return True
        except Exception as e:
            logger.exception(f"Error enforcing permissions for channel {channel.id}: {e}")
            return False
