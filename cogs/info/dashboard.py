"""Dashboard command Cog for TEST Squadron bot."""

from __future__ import annotations

import contextlib
import os

import discord
from discord import app_commands
from discord.ext import commands

from config.config_loader import ConfigLoader
from helpers.decorators import require_permission_level
from helpers.permissions_helper import PermissionLevel
from utils.logging import get_logger

logger = get_logger(__name__)


class DashboardCog(commands.Cog):
    """Expose the /dashboard slash command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="dashboard",
        description="Get a link to the Web Dashboard",
    )
    @require_permission_level(PermissionLevel.STAFF)
    async def dashboard(self, interaction: discord.Interaction) -> None:
        """Send the web dashboard link as an ephemeral response."""
        try:
            # Prefer config override if present, otherwise fall back to PUBLIC_URL env (or dev default)
            config = ConfigLoader.load_config()
            config_url = (config.get("web_dashboard") or {}).get("url") if isinstance(config, dict) else None
            dashboard_url = config_url or os.getenv("PUBLIC_URL", "http://localhost:5173")

            embed = discord.Embed(
                title="🌐 Web Admin Dashboard",
                description=(
                    f"Access the TEST Clanker's Web Dashboard:\n\n"
                    f"[Open Dashboard]({dashboard_url})\n\n"
                    f"Login with your Discord account to access Discord Server data, "
                    f"view user data, and access administrative tools."
                ),
                color=0x5865F2,  # Discord blurple
            )

            embed.set_thumbnail(
                url="https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
            )

            embed.set_footer(text="Staff+ access required • Permissions enforced by dashboard")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as exc:
            logger.exception("Failed to send /dashboard embed", exc_info=exc)

            message = "❌ Unable to retrieve dashboard link. Please contact an administrator."
            if interaction.response.is_done():
                with contextlib.suppress(Exception):
                    await interaction.followup.send(message, ephemeral=True)
            else:
                with contextlib.suppress(Exception):
                    await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Register the Dashboard cog."""
    await bot.add_cog(DashboardCog(bot))
