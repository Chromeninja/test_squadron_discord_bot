"""About command Cog for TEST Squadron bot."""

from __future__ import annotations

import contextlib

import discord
from discord import app_commands
from discord.ext import commands

from helpers.embeds import build_about_embed
from utils.logging import get_logger

logger = get_logger(__name__)


class AboutCog(commands.Cog):
    """Expose the /about slash command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="about",
        description=(
            "Shows information about the TEST Squadron bot, privacy summary, and support contact."
        ),
    )
    async def about(self, interaction: discord.Interaction) -> None:
        """Send the About embed as an ephemeral response."""

        try:
            embed = build_about_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("Failed to send /about embed", exc_info=exc)

            message = "❌ Unable to show about info right now. Please try again later."
            if interaction.response.is_done():
                with contextlib.suppress(Exception):
                    await interaction.followup.send(message, ephemeral=True)
            else:
                with contextlib.suppress(Exception):
                    await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Register the About cog."""

    await bot.add_cog(AboutCog(bot))
