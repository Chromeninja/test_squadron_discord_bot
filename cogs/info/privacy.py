"""Privacy command Cog for TEST Clanker."""

from __future__ import annotations

import contextlib

import discord
from discord import app_commands
from discord.ext import commands

from helpers.embeds import build_privacy_embed
from utils.logging import get_logger

logger = get_logger(__name__)


class PrivacyCog(commands.Cog):
    """Expose the /privacy slash command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="privacy",
        description="Shows privacy policy summary and data-rights request steps.",
    )
    async def privacy(self, interaction: discord.Interaction) -> None:
        """Send the Privacy & Data Rights embed as an ephemeral response."""
        try:
            embed = build_privacy_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("Failed to send /privacy embed", exc_info=exc)

            message = "❌ Unable to show privacy info right now. Please try again later."
            if interaction.response.is_done():
                with contextlib.suppress(Exception):
                    await interaction.followup.send(message, ephemeral=True)
            else:
                with contextlib.suppress(Exception):
                    await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Register the Privacy cog."""
    await bot.add_cog(PrivacyCog(bot))
