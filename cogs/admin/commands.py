"""
Refactored admin cog with service integration and health monitoring.
"""

import json

import discord
from discord import app_commands
from discord.ext import commands
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

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check if user has admin permissions."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False

        return await self.bot.has_admin_permissions(ctx.author)

    @app_commands.command(
        name="status",
        description="Show detailed bot health and status information"
    )
    @app_commands.describe(
        detailed="Show detailed service information"
    )
    async def status(
        self,
        interaction: discord.Interaction,
        detailed: bool = False
    ) -> None:
        """Show bot status and health metrics."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        # Check permissions
        if not await self.bot.has_admin_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
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
                timestamp=discord.utils.utcnow()
            )

            # Basic status info
            embed.add_field(
                name="Overall Status",
                value=self._format_status(health_report["overall_status"]),
                inline=True
            )

            embed.add_field(
                name="Uptime",
                value=self.bot.uptime,
                inline=True
            )

            embed.add_field(
                name="Guilds",
                value=str(health_report["discord"]["guilds"]),
                inline=True
            )

            # System metrics
            system = health_report["system"]
            embed.add_field(
                name="💻 System",
                value=f"CPU: {system['cpu_percent']:.1f}%\\n"
                      f"Memory: {system['memory_mb']:.1f} MB\\n"
                      f"Threads: {system['threads']}",
                inline=True
            )

            # Discord metrics
            discord_info = health_report["discord"]
            embed.add_field(
                name="🔗 Discord",
                value=f"Latency: {discord_info['latency_ms']}ms\\n"
                      f"Users: {discord_info['users']}\\n"
                      f"Ready: {'✅' if discord_info['is_ready'] else '❌'}",
                inline=True
            )

            # Database status
            db = health_report["database"]
            if db["connected"]:
                embed.add_field(
                    name="🗄️ Database",
                    value="✅ Connected",
                    inline=True
                )
            else:
                embed.add_field(
                    name="🗄️ Database",
                    value=f"❌ Error: {db.get('error', 'Unknown')}",
                    inline=True
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
                    inline=True
                )

            # Service status
            services = health_report.get("services", {})
            service_status = []
            for service_name, service_health in services.items():
                status = service_health.get("status", "unknown")
                emoji = "✅" if status == "healthy" else "⚠️" if status == "degraded" else "❌"
                service_status.append(f"{emoji} {service_name}")

            if service_status:
                embed.add_field(
                    name="🔧 Services",
                    value="\\n".join(service_status),
                    inline=True
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
                                value="\\n".join(details[:5]),  # Limit to avoid embed limits
                                inline=False
                            )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Error in status command: {e}")
            await interaction.followup.send(
                f"❌ Error retrieving status: {e!s}",
                ephemeral=True
            )

    @app_commands.command(
        name="guild-config",
        description="Show configuration for this guild"
    )
    async def guild_config(self, interaction: discord.Interaction) -> None:
        """Show guild-specific configuration."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        # Check permissions
        if not await self.bot.has_admin_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            config = await self.bot.get_guild_config(interaction.guild.id)

            embed = discord.Embed(
                title="⚙️ Guild Configuration",
                description=f"Configuration for **{interaction.guild.name}**",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            # Roles configuration
            roles = config.get("roles", {})
            if roles:
                role_info = []
                for role_key, role_id in roles.items():
                    if isinstance(role_id, list):
                        role_names = []
                        for rid in role_id:
                            role = interaction.guild.get_role(rid)
                            role_names.append(role.name if role else f"Unknown ({rid})")
                        role_info.append(f"{role_key}: {', '.join(role_names)}")
                    else:
                        role = interaction.guild.get_role(role_id)
                        role_name = role.name if role else f"Unknown ({role_id})"
                        role_info.append(f"{role_key}: {role_name}")

                embed.add_field(
                    name="🎭 Roles",
                    value="\\n".join(role_info[:10]),  # Limit to avoid embed limits
                    inline=False
                )

            # Channels configuration
            channels = config.get("channels", {})
            if channels:
                channel_info = []
                for channel_key, channel_id in channels.items():
                    channel = interaction.guild.get_channel(channel_id)
                    channel_name = channel.name if channel else f"Unknown ({channel_id})"
                    channel_info.append(f"{channel_key}: #{channel_name}")

                embed.add_field(
                    name="📺 Channels",
                    value="\\n".join(channel_info),
                    inline=False
                )

            # Voice settings
            voice_cooldown = await self.bot.services.config.get(
                interaction.guild.id, "voice.cooldown_seconds", parser=int
            ) or 60  # Default cooldown if not set

            embed.add_field(
                name="🔊 Voice Settings",
                value=f"Cooldown: {voice_cooldown}s",
                inline=True
            )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Error in guild-config command: {e}")
            await interaction.followup.send(
                f"❌ Error retrieving guild configuration: {e!s}",
                ephemeral=True
            )

    @app_commands.command(
        name="set-config",
        description="Set a configuration value for this guild"
    )
    @app_commands.describe(
        key="Configuration key (e.g., 'voice.cooldown_seconds')",
        value="Configuration value (JSON format)"
    )
    async def set_config(
        self,
        interaction: discord.Interaction,
        key: str,
        value: str
    ) -> None:
        """Set a guild configuration value."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        # Check permissions
        if not await self.bot.has_admin_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Parse JSON value
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                # Try as string if JSON parsing fails
                parsed_value = value

            # Set the configuration
            await self.bot.services.config.set_guild_setting(
                interaction.guild.id, key, parsed_value
            )

            embed = discord.Embed(
                title="✅ Configuration Updated",
                description=f"Set `{key}` to `{parsed_value}`",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            embed.set_footer(text=f"Updated by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Error in set-config command: {e}")
            await interaction.followup.send(
                f"❌ Error setting configuration: {e!s}",
                ephemeral=True
            )

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
