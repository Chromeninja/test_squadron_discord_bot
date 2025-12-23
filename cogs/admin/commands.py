"""
Refactored admin cog with service integration and health monitoring.
"""

import discord
from discord import app_commands
from discord.ext import commands

from helpers.decorators import require_permission_level
from helpers.permissions_helper import PermissionLevel
from utils.log_context import get_interaction_extra
from utils.logging import get_logger

logger = get_logger(__name__)


class AdminCog(commands.Cog):
    """
    Administrative commands with service integration.

    Provides health monitoring, status reporting, and administrative
    functions using the service architecture.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = get_logger(__name__)

    async def cog_check(self, ctx: commands.Context) -> bool:  # type: ignore[override]
        """Check if user has admin permissions."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False

        return await self.bot.has_admin_permissions(ctx.author)

    @app_commands.command(
        name="reset-all", description="Reset verification timers for all members."
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.BOT_ADMIN)
    async def reset_all(self, interaction: discord.Interaction) -> None:
        """
        Reset verification timers for all members. Bot Admins only.
        """
        from helpers.rate_limiter import reset_all_attempts
        from helpers.token_manager import clear_all_tokens

        self.logger.info(
            "reset-all command triggered",
            extra=get_interaction_extra(interaction),
        )

        # Defer immediately before async operations
        await interaction.response.defer(ephemeral=True)

        await reset_all_attempts()
        clear_all_tokens()

        await interaction.followup.send(
            "✅ Reset verification timers for all members.", ephemeral=True
        )

        self.logger.info(
            "reset-all command completed successfully",
            extra=get_interaction_extra(interaction),
        )

    @app_commands.command(
        name="reset-user", description="Reset verification timer for a specific user."
    )
    @app_commands.describe(member="The member whose timer you want to reset.")
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.MODERATOR)
    async def reset_user(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """
        Reset a specific user's verification timer. Bot Admins and Moderators.
        """
        from helpers.rate_limiter import reset_attempts
        from helpers.token_manager import clear_token

        self.logger.info(
            "reset-user command triggered",
            extra=get_interaction_extra(interaction, target_user_id=str(member.id)),
        )

        # Defer immediately before async operations
        await interaction.response.defer(ephemeral=True)

        await reset_attempts(member.id)
        clear_token(member.id)

        await interaction.followup.send(
            f"✅ Reset verification timer for {member.mention}.",
            ephemeral=True,
        )

        self.logger.info(
            "reset-user command completed successfully",
            extra=get_interaction_extra(interaction, target_user_id=str(member.id)),
        )

    @app_commands.command(
        name="flush-announcements",
        description="Force flush pending announcement queue immediately.",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.BOT_ADMIN)
    async def flush_announcements(self, interaction: discord.Interaction) -> None:
        """
        Force flush the pending announcement queue immediately.

        This will post all pending member join/promotion announcements to the
        public announcement channel instead of waiting for the daily scheduled time
        or threshold trigger. Bot Admins only.
        """
        self.logger.info(
            "flush-announcements command triggered",
            extra=get_interaction_extra(interaction),
        )

        await interaction.response.defer(ephemeral=True)

        try:
            # Get the BulkAnnouncer cog
            announcer = self.bot.get_cog("BulkAnnouncer")
            if not announcer:
                await interaction.followup.send(
                    "❌ BulkAnnouncer cog not loaded. Cannot flush announcements.",
                    ephemeral=True,
                )
                self.logger.error(
                    "BulkAnnouncer cog not found when flush-announcements was called"
                )
                return

            # Get pending count before flushing
            pending_count = await announcer._count_pending()

            if pending_count == 0:
                await interaction.followup.send(
                    "ℹ️ No pending announcements in queue.", ephemeral=True
                )
                self.logger.info(
                    "flush-announcements: no pending announcements",
                    extra={"user_id": interaction.user.id},
                )
                return

            # Flush the queue (guard against stale/partial BulkAnnouncer loads)
            self.logger.info(
                "flush-announcements: flushing pending events",
                extra=get_interaction_extra(interaction, pending_count=pending_count),
            )

            if not hasattr(announcer, "flush_pending") or not callable(announcer.flush_pending):
                await interaction.followup.send(
                    "❌ BulkAnnouncer is loaded but missing the flush handler. Please reload the bot/cog and try again.",
                    ephemeral=True,
                )
                self.logger.error(
                    "flush-announcements: BulkAnnouncer missing flush_pending",
                    extra=get_interaction_extra(interaction, pending_count=pending_count),
                )
                return

            sent, missing_guilds = await announcer.flush_pending()  # type: ignore[union-attr]

            # Build response message
            if sent:
                message = f"✅ Successfully flushed announcement queue! Posted {pending_count} pending event(s) to public announcement channels."
                if missing_guilds:
                    message += f"\n⚠️ Skipped {len(missing_guilds)} guild(s) missing a public announcement channel: {', '.join(str(g) for g in missing_guilds)}"
                await interaction.followup.send(message, ephemeral=True)
                self.logger.info(
                    "flush-announcements: successfully flushed events",
                    extra=get_interaction_extra(
                        interaction, pending_count=pending_count, missing_guilds=missing_guilds
                    ),
                )
            else:
                detail = (
                    f"Missing public announcement channel for guild(s): {', '.join(str(g) for g in missing_guilds)}"
                    if missing_guilds
                    else "Check that public announcement channels are configured."
                )
                await interaction.followup.send(
                    f"⚠️ Flush completed but no announcements were sent. {detail}",
                    ephemeral=True,
                )
                self.logger.warning(
                    "flush-announcements: flush returned False (no announcements sent) despite pending events",
                    extra=get_interaction_extra(
                        interaction, pending_count=pending_count, missing_guilds=missing_guilds
                    ),
                )

        except Exception:
            await interaction.followup.send(
                "❌ Failed to flush announcements. Check logs for details.", ephemeral=True
            )
            self.logger.exception(
                "flush-announcements command failed",
                extra=get_interaction_extra(interaction),
            )

    # Removed: view-logs command. Log viewing is now Web Admin only.
    # Use the web dashboard at /dashboard to export bot logs, backend logs, and audit logs.

    @app_commands.command(
        name="status", description="Show detailed bot health and status information"
    )
    @app_commands.describe(detailed="Show detailed service information")
    @require_permission_level(PermissionLevel.BOT_ADMIN)
    async def status(
        self, interaction: discord.Interaction, detailed: bool = False
    ) -> None:
        """Show bot status and health metrics."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get comprehensive health report
            health_report = await self.bot.services.health.run_health_checks(
                self.bot, self.bot.services.get_all_services()
            )
            # Create status embed
            embed = discord.Embed(
                title="🤖 Bot Status",
                color=self._get_status_color(health_report["overall_status"]),
                timestamp=discord.utils.utcnow(),
            )
            # Basic status info
            embed.add_field(
                name="Overall Status",
                value=self._format_status(health_report["overall_status"]),
                inline=True,
            )

            embed.add_field(name="Uptime", value=self.bot.uptime, inline=True)

            embed.add_field(
                name="Guilds",
                value=str(health_report["discord"]["guilds"]),
                inline=True,
            )

            # System metrics
            system = health_report["system"]
            embed.add_field(
                name="💻 System",
                value=f"CPU: {system['cpu_percent']:.1f}%\\n"
                f"Memory: {system['memory_mb']:.1f} MB\\n"
                f"Threads: {system['threads']}",
                inline=True,
            )

            # Discord metrics
            discord_info = health_report["discord"]
            embed.add_field(
                name="🔗 Discord",
                value=f"Latency: {discord_info['latency_ms']}ms\\n"
                f"Users: {discord_info['users']}\\n"
                f"Ready: {'✅' if discord_info['is_ready'] else '❌'}",
                inline=True,
            )

            # Database status
            db = health_report["database"]
            if db["connected"]:
                embed.add_field(name="🗄️ Database", value="✅ Connected", inline=True)
            else:
                embed.add_field(
                    name="🗄️ Database",
                    value=f"❌ Error: {db.get('error', 'Unknown')}",
                    inline=True,
                )

            # Bot metrics
            metrics = health_report.get("metrics", {})
            if metrics:
                embed.add_field(
                    name="📊 Metrics",
                    value=f"Commands: {metrics.get('commands_processed', 0)}\\n"
                    f"Events: {metrics.get('events_processed', 0)}\\n"
                    f"Errors: {metrics.get('errors_encountered', 0)}\\n"
                    f"Voice Channels: {metrics.get('voice_channels_created', 0)}",
                    inline=True,
                )

            # Service status
            services = health_report.get("services", {})
            service_status = []
            for service_name, service_health in services.items():
                status = service_health.get("status", "unknown")
                emoji = (
                    "✅"
                    if status == "healthy"
                    else "⚠️"
                    if status == "degraded"
                    else "❌"
                )
                service_status.append(f"{emoji} {service_name}")

            if service_status:
                embed.add_field(
                    name="🔧 Services", value="\\n".join(service_status), inline=True
                )

            # Detailed service info if requested
            if detailed and services:
                for service_name, service_health in services.items():
                    if service_name in ["config", "guild", "voice"]:
                        details = []
                        for key, value in service_health.items():
                            if key not in ["service", "status", "initialized"]:
                                details.append(f"{key}: {value}")

                        if details:
                            embed.add_field(
                                name=f"📋 {service_name.title()} Details",
                                value="\\n".join(
                                    details[:5]
                                ),  # Limit to avoid embed limits
                                inline=False,
                            )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception("Error in status command", exc_info=e)
            await interaction.followup.send(
                f"❌ Error retrieving status: {e!s}", ephemeral=True
            )

    # Removed: guild-config command. Configuration viewing is now Web Admin only.
    # Removed: set-config command. Configuration editing is now Web Admin only.
    # Removed: key_autocomplete and value_autocomplete (orphaned from set-config)

    def _get_status_color(self, status: str) -> discord.Color:
        """Get color for status embed based on overall status."""
        if status == "healthy":
            return discord.Color.green()
        elif status == "degraded":
            return discord.Color.yellow()
        else:
            return discord.Color.red()

    def _format_status(self, status: str) -> str:
        """Format status with emoji."""
        if status == "healthy":
            return "✅ Healthy"
        elif status == "degraded":
            return "⚠️ Degraded"
        else:
            return "❌ Unhealthy"


async def setup(bot) -> None:
    """Setup function for the cog."""
    await bot.add_cog(AdminCog(bot))
