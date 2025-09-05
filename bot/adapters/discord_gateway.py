# Bot/adapters/discord_gateway.py

import discord
from typing import Optional, Dict, Union
from helpers.logger import get_logger
from helpers.retry import retry_async, RetryConfig
import helpers.discord_api as discord_api

logger = get_logger(__name__)


class DiscordGateway:
    """
    Centralized gateway for Discord interactions.
    
    This class provides a unified interface for Discord operations,
    internally delegating to helpers.discord_api.py functions while
    maintaining consistent error handling and logging.
    """

    def __init__(self, bot):
        """
        Initialize the Discord gateway.
        
        Args:
            bot: The Discord bot instance
        """
        self.bot = bot
        # Default retry configuration for Discord operations
        self.retry_config = RetryConfig(
            max_attempts=3,
            base_delay=0.5,
            max_delay=5.0,
            jitter_factor=0.1,
            backoff_multiplier=2.0
        )
        logger.info("DiscordGateway initialized")

    async def create_voice_channel(
        self,
        guild: discord.Guild,
        name: str,
        category: discord.CategoryChannel,
        user_limit: Optional[int] = None,
        overwrites: Optional[Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite]] = None
    ) -> discord.VoiceChannel:
        """
        Create a voice channel in the specified guild and category.
        
        Args:
            guild: The guild to create the channel in
            name: The name of the channel
            category: The category to place the channel in
            user_limit: Maximum number of users (None for unlimited)
            overwrites: Permission overwrites
            
        Returns:
            The created voice channel
        """
        return await retry_async(
            discord_api.create_voice_channel,
            guild=guild,
            name=name,
            category=category,
            user_limit=user_limit,
            overwrites=overwrites,
            config=self.retry_config,
            operation_name=f"create_voice_channel({name})"
        )

    async def delete_channel(self, channel: discord.abc.GuildChannel) -> None:
        """
        Delete a Discord channel.
        
        Args:
            channel: The channel to delete
        """
        await retry_async(
            discord_api.delete_channel,
            channel,
            config=self.retry_config,
            operation_name=f"delete_channel({channel.name})"
        )

    async def edit_channel(self, channel: discord.abc.GuildChannel, **kwargs) -> None:
        """
        Edit a Discord channel.
        
        Args:
            channel: The channel to edit
            **kwargs: Channel properties to update
        """
        await retry_async(
            discord_api.edit_channel,
            channel,
            config=self.retry_config,
            operation_name=f"edit_channel({channel.name})",
            **kwargs
        )

    async def move_member(self, member: discord.Member, channel: discord.VoiceChannel) -> None:
        """
        Move a member to a voice channel.
        
        Args:
            member: The member to move
            channel: The destination voice channel
        """
        await retry_async(
            discord_api.move_member,
            member,
            channel,
            config=self.retry_config,
            operation_name=f"move_member({member.display_name})"
        )

    async def add_roles(self, member: discord.Member, *roles, reason: Optional[str] = None) -> None:
        """
        Add roles to a member.
        
        Args:
            member: The member to add roles to
            *roles: The roles to add
            reason: The reason for adding roles
        """
        await retry_async(
            discord_api.add_roles,
            member,
            *roles,
            reason=reason,
            config=self.retry_config,
            operation_name=f"add_roles({member.display_name})"
        )

    async def remove_roles(self, member: discord.Member, *roles, reason: Optional[str] = None) -> None:
        """
        Remove roles from a member.
        
        Args:
            member: The member to remove roles from
            *roles: The roles to remove
            reason: The reason for removing roles
        """
        await retry_async(
            discord_api.remove_roles,
            member,
            *roles,
            reason=reason,
            config=self.retry_config,
            operation_name=f"remove_roles({member.display_name})"
        )

    async def edit_member(self, member: discord.Member, **kwargs) -> None:
        """
        Edit a member's properties.
        
        Args:
            member: The member to edit
            **kwargs: Member properties to update
        """
        await retry_async(
            discord_api.edit_member,
            member,
            config=self.retry_config,
            operation_name=f"edit_member({member.display_name})",
            **kwargs
        )

    async def send_interaction_message(
        self,
        interaction: discord.Interaction,
        content: str,
        ephemeral: bool = False,
        embed: Optional[discord.Embed] = None,
        view: Optional[discord.ui.View] = None
    ) -> None:
        """
        Send a message in response to an interaction.
        
        Args:
            interaction: The interaction to respond to
            content: The message content
            ephemeral: Whether the message should be ephemeral
            embed: Optional embed to include
            view: Optional view to include
        """
        await retry_async(
            discord_api.send_message,
            interaction=interaction,
            content=content,
            ephemeral=ephemeral,
            embed=embed,
            view=view,
            config=self.retry_config,
            operation_name="send_interaction_message"
        )

    async def channel_send_message(
        self,
        channel: discord.TextChannel,
        content: str,
        embed: Optional[discord.Embed] = None,
        view: Optional[discord.ui.View] = None
    ) -> None:
        """
        Send a message to a text channel.
        
        Args:
            channel: The channel to send the message to
            content: The message content
            embed: Optional embed to include
            view: Optional view to include
        """
        await retry_async(
            discord_api.channel_send_message,
            channel=channel,
            content=content,
            embed=embed,
            view=view,
            config=self.retry_config,
            operation_name=f"channel_send_message({channel.name})"
        )
