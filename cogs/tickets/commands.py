"""
Ticket slash commands — /tickets group.

Configuration (channel, panel text, log channel, close message,
staff roles, categories) is managed entirely through the web
dashboard.  This cog handles:
    /tickets stats    — Show ticket statistics (Staff+)
    /tickets health   — Show thread health status (Staff+)
    /tickets cleanup  — Clean up old closed ticket threads (Bot Admin)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord  # type: ignore[import-not-found]
from discord import app_commands  # type: ignore[import-not-found]
from discord.ext import commands, tasks  # type: ignore[import-not-found]

from helpers.decorators import require_permission_level
from helpers.discord_api import channel_send_message
from helpers.embeds import EmbedColors, create_embed
from helpers.leadership_log import resolve_leadership_channel
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

# Panel message IDs are stored per (guild, channel) pair using the key
# pattern ``tickets.panel_message_id.<channel_id>`` in guild_settings.
# The legacy key ``tickets.panel_message_id`` (no channel suffix) is also
# loaded for backward compatibility.

_PANEL_KEY_PREFIX = "tickets.panel_message_id"


async def _load_panel_message_ids() -> dict[tuple[int, int], int]:
    """Load ticket panel message IDs for all (guild, channel) pairs.

    Returns:
        Mapping of ``(guild_id, channel_id)`` → ``message_id``.
    """
    ids: dict[tuple[int, int], int] = {}
    try:
        rows = await BaseRepository.fetch_all(
            "SELECT guild_id, key, value FROM guild_settings "
            "WHERE key LIKE 'tickets.panel_message_id%'"
        )
        for row in rows:
            try:
                guild_id = int(row[0])
                key = str(row[1])
                msg_id = int(row[2])
                # Parse channel_id from key suffix
                if key == _PANEL_KEY_PREFIX:
                    # Legacy key — channel_id unknown, use 0 as placeholder
                    channel_id = 0
                elif key.startswith(f"{_PANEL_KEY_PREFIX}."):
                    channel_id = int(key.split(".")[-1])
                else:
                    continue
                ids[(guild_id, channel_id)] = msg_id
            except (ValueError, TypeError, IndexError):
                pass
        logger.info("Loaded %d ticket panel message IDs from database", len(ids))
    except Exception as e:
        logger.exception("Failed to load ticket panel message IDs", exc_info=e)
    return ids


async def _save_panel_message_id(
    guild_id: int, channel_id: int, message_id: int
) -> None:
    """Persist a ticket panel message ID for a (guild, channel) pair."""
    key = f"{_PANEL_KEY_PREFIX}.{channel_id}"
    try:
        await BaseRepository.execute(
            "INSERT INTO guild_settings (guild_id, key, value) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
            (guild_id, key, str(message_id)),
        )
    except Exception as e:
        logger.exception(
            "Failed to save ticket panel message ID for guild %s channel %s",
            guild_id,
            channel_id,
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
        # Track last alert level per guild to avoid duplicate alerts
        self._last_alert_level: dict[int, str] = {}
        # Ensure panels exist on startup
        spawn(self._wait_and_ensure_panels())
        # Start periodic session cleanup
        self._session_cleanup_task.start()  # pylint: disable=no-member
        # Start periodic thread health monitoring
        self._thread_health_check_task.start()  # pylint: disable=no-member

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
    # Periodic thread health monitoring (every 12 hours)
    # ------------------------------------------------------------------

    @tasks.loop(hours=12)
    async def _thread_health_check_task(self) -> None:
        """Check thread usage across all guilds and alert if thresholds are met.

        AI Notes:
            Only sends an alert when the severity *escalates* compared to
            the last alert for that guild, avoiding duplicate notifications.
            Alerts mention bot admin roles so they get pinged.
        """
        for guild in self.bot.guilds:
            try:
                health = await self.ticket_service.get_thread_health(guild.id)
                status = health["status"]

                # Only alert on non-healthy statuses
                if status == "healthy":
                    # Reset tracker so a future escalation triggers again
                    self._last_alert_level.pop(guild.id, None)
                    continue

                # Avoid duplicate alerts for the same severity
                severity_order = {"notice": 1, "warning": 2, "critical": 3}
                current = severity_order.get(status, 0)
                last = severity_order.get(
                    self._last_alert_level.get(guild.id, ""), 0
                )
                if current <= last:
                    continue

                self._last_alert_level[guild.id] = status
                await self._send_thread_health_alert(guild, health)
            except Exception as e:
                self.logger.exception(
                    "Thread health check failed for guild %s",
                    guild.id,
                    exc_info=e,
                )

    @_thread_health_check_task.before_loop
    async def _before_thread_health_check(self) -> None:
        """Wait for the bot to be ready before starting health checks."""
        await self.bot.wait_until_ready()

    async def _send_thread_health_alert(
        self,
        guild: discord.Guild,
        health: dict[str, object],
    ) -> None:
        """Post a thread-health alert to the leadership channel.

        Mentions bot-admin roles so they are pinged.
        """
        status = str(health["status"])
        usage_pct = health["usage_pct"]
        total = health["total_threads"]
        limit = health["limit"]

        status_emoji = {
            "notice": "📢",
            "warning": "⚠️",
            "critical": "🚨",
        }
        emoji = status_emoji.get(status, "ℹ️")

        # Build admin role mentions
        guild_config = self.bot.services.guild_config
        admin_roles = await guild_config.get_admin_roles(guild.id, guild)
        mentions = " ".join(r.mention for r in admin_roles)

        embed = create_embed(
            title=f"{emoji} Thread Limit {status.upper()}",
            description=(
                f"**Guild:** {guild.name}\n"
                f"**Thread Usage:** {total} / {limit} ({usage_pct}%)\n"
                f"**Active Tickets:** {health['active']}\n"
                f"**Archived Threads:** {health['archived']}\n\n"
                "Use `/tickets health` for details or "
                "`/tickets cleanup` to remove old threads."
            ),
            color=(
                EmbedColors.ERROR
                if status == "critical"
                else EmbedColors.WARNING
            ),
        )

        channel = await resolve_leadership_channel(self.bot, guild.id)
        if channel:
            content = mentions if mentions else None
            # Send directly (not via channel_send_message) so role
            # mentions are allowed in the alert ping.
            await channel.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            self.logger.info(
                "Sent thread health %s alert for guild %s (%s%%)",
                status,
                guild.id,
                usage_pct,
            )
        else:
            self.logger.warning(
                "No leadership channel for guild %s — skipping thread alert",
                guild.id,
            )

    # ------------------------------------------------------------------
    # Startup — ensure panel messages exist
    # ------------------------------------------------------------------

    async def _wait_and_ensure_panels(self) -> None:
        """Wait for the bot to be ready, then verify panel messages."""
        await self.bot.wait_until_ready()
        await self._ensure_panels()

    async def _ensure_panels(self, guilds: list[discord.Guild] | None = None) -> None:
        """For each guild, ensure a panel exists in every channel that has categories.

        AI Notes:
            Discovers ticket channels from the ``channel_id`` column on
            ``ticket_categories`` rather than a single guild setting.
            Falls back to the legacy ``tickets.channel_id`` setting if
            no categories specify a channel.
        """
        targets = guilds or self.bot.guilds
        panel_ids = await _load_panel_message_ids()

        for guild in targets:
            try:
                # Discover all channels that have ticket categories
                channel_ids = await self.ticket_service.get_ticket_channel_ids(
                    guild.id
                )

                # Fall back to legacy single-channel setting
                if not channel_ids:
                    legacy_id = await self.config_service.get_guild_setting(
                        guild.id, "tickets.channel_id"
                    )
                    if legacy_id:
                        channel_ids = [int(legacy_id)]

                if not channel_ids:
                    continue

                for chan_id in channel_ids:
                    channel = guild.get_channel(chan_id)
                    if channel is None or not isinstance(
                        channel, discord.TextChannel
                    ):
                        continue

                    existing_msg_id = panel_ids.get((guild.id, chan_id))
                    if existing_msg_id:
                        try:
                            await channel.fetch_message(existing_msg_id)
                            continue  # panel still exists
                        except discord.NotFound:
                            logger.debug(
                                "Ticket panel %s missing in guild %s channel %s",
                                existing_msg_id,
                                guild.id,
                                chan_id,
                                exc_info=True,
                            )

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
        channel_config = await self.ticket_service.get_channel_config(
            guild.id, channel.id
        )
        title = (
            (channel_config or {}).get("panel_title")
            or "🎫 Support Tickets"
        )
        description = (
            (channel_config or {}).get("panel_description")
            or (
                "Need help? Click the button below to open a support ticket.\n\n"
                "A private thread will be created for you and a staff member "
                "will assist you as soon as possible."
            )
        )

        embed = create_embed(
            title=title,
            description=description,
            color=EmbedColors.INFO,
        )
        view = TicketPanelView(
            self.bot,
            private_button_text=(channel_config or {}).get(
                "button_text", "Create Ticket"
            ),
            private_button_emoji=(channel_config or {}).get("button_emoji", "🎫"),
            enable_public_button=bool(
                (channel_config or {}).get("enable_public_button", 0)
            ),
            public_button_text=(channel_config or {}).get(
                "public_button_text", "Create Public Ticket"
            ),
            public_button_emoji=(channel_config or {}).get(
                "public_button_emoji", "🌐"
            ),
            private_button_color=(channel_config or {}).get("private_button_color"),
            public_button_color=(channel_config or {}).get("public_button_color"),
            button_order=(channel_config or {}).get("button_order", "private_first"),
        )

        try:
            msg = await channel.send(embed=embed, view=view)
            await _save_panel_message_id(guild.id, channel.id, msg.id)
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
        """Display ticket counts and thread usage."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        assert guild is not None

        data = await self.ticket_service.get_ticket_stats(guild.id)
        health = await self.ticket_service.get_thread_health(guild.id)
        embed = create_embed(
            title="🎫 Ticket Statistics",
            description=(
                f"**Open:** {data['open']}\n"
                f"**Closed:** {data['closed']}\n"
                f"**Total:** {data['total']}\n\n"
                f"📌 **Discord Threads:** {health['total_threads']} / "
                f"{health['limit']} ({health['usage_pct']}%)"
            ),
            color=EmbedColors.INFO,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /tickets health
    # ------------------------------------------------------------------

    @app_commands.command(
        name="health",
        description="Show thread health and cleanup candidates.",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.STAFF)
    async def health(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Display thread usage status and oldest closed tickets."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        assert guild is not None

        health = await self.ticket_service.get_thread_health(guild.id)
        oldest = await self.ticket_service.get_oldest_closed_tickets(
            guild.id, limit=5
        )

        status_emoji = {
            "healthy": "✅",
            "notice": "📢",
            "warning": "⚠️",
            "critical": "🚨",
        }
        emoji = status_emoji.get(health["status"], "ℹ️")

        lines = [
            f"**Status:** {emoji} {health['status'].upper()}",
            f"**Thread Usage:** {health['total_threads']} / "
            f"{health['limit']} ({health['usage_pct']}%)",
            f"**Active Tickets:** {health['active']}",
            f"**Archived Threads:** {health['archived']}",
            f"**Deleted Threads:** {health['deleted']}",
        ]

        if oldest:
            lines.append("\n**Oldest Closed Tickets (cleanup candidates):**")
            for t in oldest:
                closed_ts = t.get("closed_at")
                if closed_ts:
                    days_ago = (int(time.time()) - int(closed_ts)) // 86400
                    lines.append(
                        f"• <#{t['thread_id']}> — closed {days_ago}d ago"
                    )

        embed = create_embed(
            title="🏥 Thread Health",
            description="\n".join(lines),
            color=(
                EmbedColors.SUCCESS
                if health["status"] == "healthy"
                else EmbedColors.WARNING
                if health["status"] in ("notice", "warning")
                else EmbedColors.ERROR
            ),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /tickets cleanup
    # ------------------------------------------------------------------

    @app_commands.command(
        name="cleanup",
        description="Delete old closed ticket threads to free up space.",
    )
    @app_commands.describe(
        older_than="Minimum days since ticket was closed (min 30).",
        dry_run="Preview only — do not actually delete threads.",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.BOT_ADMIN)
    async def cleanup(
        self,
        interaction: discord.Interaction,
        older_than: int = 90,
        dry_run: bool = True,
    ) -> None:
        """Delete Discord threads for old closed tickets.

        AI Notes:
            ``dry_run`` defaults to ``True`` so admins must explicitly
            opt in to destructive actions.  The 30-day minimum is
            enforced by the service layer.
        """
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        assert guild is not None

        candidates = await self.ticket_service.get_cleanup_candidates(
            guild.id, older_than_days=older_than
        )

        if not candidates:
            embed = create_embed(
                title="🧹 Cleanup — Nothing to do",
                description=(
                    f"No closed tickets older than {max(older_than, 30)} "
                    "days found."
                ),
                color=EmbedColors.INFO,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if dry_run:
            lines = [
                f"Found **{len(candidates)}** thread(s) eligible for deletion "
                f"(closed >{max(older_than, 30)} days ago):\n"
            ]
            for t in candidates[:25]:  # cap preview
                closed_ts = t.get("closed_at")
                days_ago = (
                    (int(time.time()) - int(closed_ts)) // 86400
                    if closed_ts
                    else "?"
                )
                lines.append(
                    f"• <#{t['thread_id']}> — closed {days_ago}d ago"
                )
            if len(candidates) > 25:
                lines.append(
                    f"\n…and {len(candidates) - 25} more."
                )
            lines.append(
                "\nRe-run with `dry_run: False` to delete these threads."
            )
            embed = create_embed(
                title="🧹 Cleanup — Dry Run",
                description="\n".join(lines),
                color=EmbedColors.WARNING,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Actual deletion
        deleted = 0
        failed = 0
        for t in candidates:
            thread_id = t["thread_id"]
            try:
                thread = guild.get_thread(thread_id)
                if thread is None:
                    # Thread already gone from Discord — just mark it
                    await self.ticket_service.mark_thread_deleted(thread_id)
                    deleted += 1
                    continue
                await thread.delete()
                await self.ticket_service.mark_thread_deleted(thread_id)
                deleted += 1
            except discord.NotFound:
                # Already deleted in Discord
                await self.ticket_service.mark_thread_deleted(thread_id)
                deleted += 1
            except Exception as e:
                self.logger.exception(
                    "Failed to delete thread %s", thread_id, exc_info=e
                )
                failed += 1

        desc = f"Deleted **{deleted}** thread(s)."
        if failed:
            desc += f"\n**{failed}** thread(s) could not be deleted."

        embed = create_embed(
            title="🧹 Cleanup Complete",
            description=desc,
            color=EmbedColors.SUCCESS if not failed else EmbedColors.WARNING,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log to leadership channel
        channel = await resolve_leadership_channel(self.bot, guild.id)
        if channel:
            log_embed = create_embed(
                title="🧹 Ticket Thread Cleanup",
                description=(
                    f"**Admin:** {interaction.user.mention}\n"
                    f"**Deleted:** {deleted} thread(s)\n"
                    f"**Failed:** {failed}\n"
                    f"**Criteria:** closed >{max(older_than, 30)} days"
                ),
                color=EmbedColors.INFO,
            )
            await channel_send_message(channel, "", embed=log_embed)


async def setup(bot: MyBot) -> None:
    """Register the Tickets cog."""
    await bot.add_cog(TicketCommands(bot))


async def teardown(bot: MyBot) -> None:
    """Unregister the Tickets cog and stop background tasks."""
    cog = bot.get_cog("tickets")
    if isinstance(cog, TicketCommands):
        cog._session_cleanup_task.cancel()  # pylint: disable=no-member
        cog._thread_health_check_task.cancel()  # pylint: disable=no-member
