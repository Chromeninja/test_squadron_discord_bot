"""
Voice Events Cog

Handles Discord voice state events and delegates to the VoiceService.
"""

from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from utils.logging import get_logger

if TYPE_CHECKING:
    from services.service_container import ServiceContainer

logger = get_logger(__name__)


class VoiceEvents(commands.Cog):
    """Handles voice state change events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.services: ServiceContainer | None = None

    @property
    def voice_service(self):
        """Get the voice service from the bot's service container."""
        if not hasattr(self.bot, "services") or self.bot.services is None:
            raise RuntimeError("Bot services not initialized")
        return self.bot.services.voice

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state changes for join-to-create functionality."""
        try:
            # Delegate to voice service
            await self.voice_service.handle_voice_state_change(
                member=member,
                before_channel=before.channel,
                after_channel=after.channel,
            )

        except Exception as e:
            logger.exception(
                f"Error handling voice state update for {member} "
                f"(before: {before.channel}, after: {after.channel}): {e}"
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Handle channel deletion to clean up database records."""
        if not isinstance(channel, discord.VoiceChannel):
            return

        try:
            await self.voice_service.handle_channel_deleted(
                guild_id=channel.guild.id, channel_id=channel.id
            )

        except Exception as e:
            logger.exception("Error handling channel deletion for %s", channel, exc_info=e)


async def setup(bot: commands.Bot) -> None:
    """Set up the Voice Events cog."""
    await bot.add_cog(VoiceEvents(bot))
