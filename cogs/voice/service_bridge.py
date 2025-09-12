"""
Voice Service Bridge

Provides compatibility layer and convenience methods for voice operations.
This bridges the gap between the old cog structure and the new service-based architecture.
"""

from typing import TYPE_CHECKING

from discord.ext import commands
from utils.logging import get_logger

if TYPE_CHECKING:
    from services.service_container import ServiceContainer

logger = get_logger(__name__)


class VoiceServiceBridge(commands.Cog):
    """Bridge between legacy voice operations and new service architecture."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.services: ServiceContainer | None = None

    @property
    def voice_service(self):
        """Get the voice service from the bot's service container."""
        if not hasattr(self.bot, 'services') or self.bot.services is None:
            raise RuntimeError("Bot services not initialized")
        return self.bot.services.voice

    async def cog_load(self) -> None:
        """Initialize the voice service bridge."""
        logger.info("Voice service bridge loaded")

    async def initialize_voice_channels(self, guild_id: int) -> None:
        """Initialize voice channels for a guild."""
        await self.voice_service.initialize_guild_voice_channels(guild_id)

    async def get_user_voice_channel(self, guild_id: int, user_id: int):
        """Get a user's active voice channel."""
        return await self.voice_service.get_user_voice_channel_info(guild_id, user_id)

    async def cleanup_stale_channels(self, guild_id: int) -> None:
        """Clean up stale voice channels for a guild."""
        await self.voice_service.cleanup_inactive_channels(guild_id)


async def setup(bot: commands.Bot) -> None:
    """Set up the Voice Service Bridge cog."""
    await bot.add_cog(VoiceServiceBridge(bot))
