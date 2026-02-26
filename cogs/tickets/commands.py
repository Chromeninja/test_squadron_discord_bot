"""
Ticket slash commands — /tickets group.

Configuration (channel, panel text, log channel, close message,
staff roles, categories) is managed entirely through the web
dashboard.  This cog handles:
    /tickets stats  — Show ticket statistics (Staff+)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord  # type: ignore[import-not-found]
from discord import app_commands  # type: ignore[import-not-found]
from discord.ext import commands, tasks  # type: ignore[import-not-found]

from helpers.decorators import require_permission_level
from helpers.embeds import EmbedColors, create_embed
from helpers.permissions_helper import PermissionLevel
from helpers.ticket_views import TicketPanelView
from services.db.repository import BaseRepository
from utils.logging import get_logger
from utils.tasks import spawn

if TYPE_CHECKING:
    from bot import MyBot
    from services.config_service import ConfigService
    from services.ticket_form_service import TicketFormService
    from services.ticket_service import TicketService

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DB helpers for panel message ID persistence
# ---------------------------------------------------------------------------


async def _load_panel_message_ids() -> dict[int, int]:
    """Load ticket panel message IDs for all guilds from the DB."""
    ids: dict[int, int] = {}
    try:
        rows = await BaseRepository.fetch_all(
            "SELECT guild_id, value FROM guild_settings WHERE key = 'tickets.panel_message_id'"
        )
        for row in rows:
            try:
                ids[int(row[0])] = int(row[1])
            except (ValueError, TypeError):
                pass
        logger.info("Loaded %d ticket panel message IDs from database", len(ids))
    except Exception as e:
        logger.exception("Failed to load ticket panel message IDs", exc_info=e)
    return ids


async def _save_panel_message_id(guild_id: int, message_id: int) -> None:
    """Persist a ticket panel message ID for a guild."""
    try:
        await BaseRepository.execute(
            "INSERT INTO guild_settings (guild_id, key, value) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
            (guild_id, "tickets.panel_message_id", str(message_id)),
        )
    except Exception as e:
        logger.exception(
            "Failed to save ticket panel message ID for guild %s",
            guild_id,
            exc_info=e,
        )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class TicketCommands(commands.GroupCog, name="tickets"):
    """Slash command group for managing the ticketing system."""

    def __init__(self, bot: MyBot) -> None:
        super().__init__()
        self.bot = bot
        self.logger = get_logger(__name__)
        # Ensure panels exist on startup
        spawn(self._wait_and_ensure_panels())
        # Start periodic session cleanup
        self._session_cleanup_task.start()  # pylint: disable=no-member

    @property
    def ticket_service(self) -> TicketService:
        """Shortcut to TicketService."""
        if not hasattr(self.bot, "services") or self.bot.services is None:
            raise RuntimeError("Bot services not initialized")
        return self.bot.services.ticket

    @property
    def config_service(self) -> ConfigService:
        """Shortcut to ConfigService."""
        return self.bot.services.config

    @property
    def ticket_form_service(self) -> TicketFormService:
        """Shortcut to TicketFormService."""
        return self.bot.services.ticket_form

    # ------------------------------------------------------------------
    # Periodic cleanup of expired route sessions
    # ------------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def _session_cleanup_task(self) -> None:
        """Periodically remove expired ticket route sessions."""
        try:
            await self.ticket_form_service.cleanup_expired_sessions()
        except Exception as e:
            self.logger.exception(
                "Error during ticket route session cleanup", exc_info=e
            )

    @_session_cleanup_task.before_loop
    async def _before_session_cleanup(self) -> None:
        """Wait for the bot to be ready before starting cleanup."""
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Startup — ensure panel messages exist
    # ------------------------------------------------------------------

    async def _wait_and_ensure_panels(self) -> None:
        """Wait for the bot to be ready, then verify panel messages."""
        await self.bot.wait_until_ready()
        await self._ensure_panels()

    async def _ensure_panels(self, guilds: list[discord.Guild] | None = None) -> None:
        """For each guild that has a ticket channel configured, ensure the panel exists."""
        targets = guilds or self.bot.guilds
        panel_ids = await _load_panel_message_ids()

        for guild in targets:
            try:
                channel_id = await self.config_service.get_guild_setting(
                    guild.id, "tickets.channel_id"
                )
                if not channel_id:
                    continue

                channel = guild.get_channel(int(channel_id))
                if channel is None or not isinstance(channel, discord.TextChannel):
                    continue

                existing_msg_id = panel_ids.get(guild.id)
                if existing_msg_id:
                    try:
                        await channel.fetch_message(existing_msg_id)
                        continue  # panel still exists
                    except discord.NotFound:
                        pass  # panel deleted — re-send

                # Send a new panel
                await self._send_panel(guild, channel)
            except Exception as e:
                logger.exception(
                    "Error ensuring ticket panel for guild %s",
                    guild.id,
                    exc_info=e,
                )

    async def _send_panel(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
    ) -> discord.Message | None:
        """Create and send the ticket panel embed + view to a channel."""
        title = await self.config_service.get_guild_setting(
            guild.id, "tickets.panel_title", default="🎫 Support Tickets"
        )
        description = await self.config_service.get_guild_setting(
            guild.id,
            "tickets.panel_description",
            default=(
                "Need help? Click the button below to open a support ticket.\n\n"
                "A private thread will be created for you and a staff member "
                "will assist you as soon as possible."
            ),
        )

        embed = create_embed(
            title=title,
            description=description,
            color=EmbedColors.INFO,
        )
        view = TicketPanelView(self.bot)

        try:
            msg = await channel.send(embed=embed, view=view)
            await _save_panel_message_id(guild.id, msg.id)
            logger.info(
                "Sent ticket panel in guild %s channel %s (msg %s)",
                guild.id,
                channel.id,
                msg.id,
            )
            return msg
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to send ticket panel in guild %s channel %s",
                guild.id,
                channel.id,
            )
        except Exception as e:
            logger.exception(
                "Failed to send ticket panel in guild %s", guild.id, exc_info=e
            )
        return None

    # ------------------------------------------------------------------
    # /tickets stats
    # ------------------------------------------------------------------

    @app_commands.command(
        name="stats",
        description="Show ticket statistics for this server.",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.STAFF)
    async def stats(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Display ticket counts."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        assert guild is not None

        data = await self.ticket_service.get_ticket_stats(guild.id)
        embed = create_embed(
            title="🎫 Ticket Statistics",
            description=(
                f"**Open:** {data['open']}\n"
                f"**Closed:** {data['closed']}\n"
                f"**Total:** {data['total']}"
            ),
            color=EmbedColors.INFO,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: MyBot) -> None:
    """Register the Tickets cog."""
    await bot.add_cog(TicketCommands(bot))


async def teardown(bot: MyBot) -> None:
    """Unregister the Tickets cog and stop background tasks."""
    cog = bot.get_cog("tickets")
    if isinstance(cog, TicketCommands):
        cog._session_cleanup_task.cancel()  # pylint: disable=no-member
