# cogs/admin/verify_bulk.py

import io
import time

import discord
from discord import app_commands
from discord.ext import commands

from helpers.bulk_check import (
    build_summary_embed,
    collect_targets,
    fetch_status_rows,
    write_csv,
)
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from utils.logging import get_logger

logger = get_logger(__name__)


class VerifyCommands(app_commands.Group):
    """Verification-related admin commands."""

    def __init__(self, bot: commands.Bot):
        super().__init__(name="verify", description="Verification management commands")
        self.bot = bot

    @app_commands.command(
        name="check",
        description="Check verification status for users (Bot Admins & Lead Moderators only)"
    )
    @app_commands.describe(
        targets="Target selection mode",
        members_text="User mentions/IDs (required for 'users' mode)",
        channel="Voice channel to check (required for 'voice_channel' mode)",
        show_details="Include detailed status information in the response",
        export_csv="Send detailed CSV results via DM"
    )
    @app_commands.choices(targets=[
        app_commands.Choice(name="specific users", value="users"),
        app_commands.Choice(name="voice channel", value="voice_channel"),
        app_commands.Choice(name="all active voice", value="active_voice")
    ])
    @app_commands.guild_only()
    async def check_verification_status(
        self,
        interaction: discord.Interaction,
        targets: app_commands.Choice[str],
        members_text: str | None = None,
        channel: discord.VoiceChannel | None = None,
        show_details: bool = False,
        export_csv: bool = False
    ) -> None:
        """Check verification status for multiple users without making changes."""

        # Permission check
        if not await self.bot.has_admin_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        # Defer response immediately as this might take some time
        await interaction.response.defer(ephemeral=True)

        start_time = time.monotonic()

        try:
            # Validate parameters based on targets mode
            targets_value = targets.value
            if targets_value == "users" and not members_text:
                await interaction.followup.send(
                    "❌ **members_text** is required when using 'specific users' mode.\n"
                    "Example: `@user1 @user2 123456789012345678`",
                    ephemeral=True
                )
                return

            if targets_value == "voice_channel" and not channel:
                await interaction.followup.send(
                    "❌ **channel** is required when using 'voice channel' mode.",
                    ephemeral=True
                )
                return

            # Collect target members
            try:
                members = await collect_targets(
                    targets_value,
                    interaction.guild,
                    members_text,
                    channel
                )
            except Exception as e:
                logger.exception(f"Error collecting targets: {e}")
                await interaction.followup.send(
                    f"❌ Error collecting target members: {e!s}",
                    ephemeral=True
                )
                return

            if not members:
                if targets_value == "users":
                    await interaction.followup.send(
                        "❌ No valid members found. Make sure to use proper mentions or valid user IDs.\n"
                        "Example: `@user1 @user2 123456789012345678`",
                        ephemeral=True
                    )
                elif targets_value == "voice_channel":
                    await interaction.followup.send(
                        "❌ The selected voice channel is empty.",
                        ephemeral=True
                    )
                else:  # active_voice
                    await interaction.followup.send(
                        "❌ No members found in any active voice channels.",
                        ephemeral=True
                    )
                return

            # Check against rate limit cap
            max_users = self.bot.config.get("auto_recheck", {}).get("batch", {}).get("max_users_per_run", 50)
            if len(members) > max_users:
                await interaction.followup.send(
                    f"❌ Too many members selected ({len(members)}). "
                    f"Maximum allowed per run: {max_users}. "
                    f"Please use a more targeted selection.",
                    ephemeral=True
                )
                return

            # Fetch verification status data
            try:
                status_rows = await fetch_status_rows(members)
            except Exception as e:
                logger.exception(f"Error fetching status data: {e}")
                await interaction.followup.send(
                    f"❌ Error fetching verification data: {e!s}",
                    ephemeral=True
                )
                return

            # Build summary embed (truncation is handled dynamically inside)
            try:
                embed = build_summary_embed(
                    invoker=interaction.user,
                    members=members,
                    rows=status_rows,
                    show_details=show_details,
                    truncated_count=0  # Will be calculated dynamically inside the function
                )
            except Exception as e:
                logger.exception(f"Error building embed: {e}")
                await interaction.followup.send(
                    f"❌ Error formatting results: {e!s}",
                    ephemeral=True
                )
                return

            # Send the main response
            response_parts = []
            if export_csv and status_rows:
                response_parts.append("📊 Results summary below. CSV with full details will be sent via DM.")

            response_content = "\n".join(response_parts) if response_parts else None

            await interaction.followup.send(
                content=response_content,
                embed=embed,
                ephemeral=True
            )

            # Handle CSV export if requested
            if export_csv and status_rows:
                try:
                    filename, content_bytes = await write_csv(status_rows)

                    # Create a BytesIO object from the content bytes
                    csv_file = discord.File(
                        fp=io.BytesIO(content_bytes),
                        filename=filename
                    )

                    # Try to send DM
                    try:
                        await interaction.user.send(
                            f"📊 Verification status export from {interaction.guild.name}",
                            file=csv_file
                        )
                    except (discord.Forbidden, discord.HTTPException) as dm_error:
                        logger.warning(f"Could not DM CSV to user {interaction.user.id}: {dm_error}")
                        await interaction.followup.send(
                            "⚠️ Could not send CSV via DM. Please ensure your DMs are open.",
                            ephemeral=True
                        )

                except Exception as e:
                    logger.exception(f"Error generating CSV: {e}")
                    await interaction.followup.send(
                        f"⚠️ Error generating CSV export: {e!s}",
                        ephemeral=True
                    )

            # Log to leadership channel
            try:
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # Count by status for summary
                status_counts = {}
                for row in status_rows:
                    status = row.membership_status or "not_in_db"
                    status_counts[status] = status_counts.get(status, 0) + 1

                # Format summary for leadership log
                count_parts = []
                for status, count in sorted(status_counts.items()):
                    display_status = {
                        "main": "Verified/Main",
                        "affiliate": "Affiliate",
                        "non_member": "Non-Member",
                        "unknown": "Unverified",
                        "unverified": "Unverified",
                        "not_in_db": "Not in DB"
                    }.get(status, status.title())
                    count_parts.append(f"{display_status}: {count}")

                summary_text = f"Checked {len(status_rows)} members. {', '.join(count_parts)}"

                # Post leadership log entry
                changeset = ChangeSet(
                    user_id=0,  # Bulk operation, no single user
                    event=EventType.ADMIN_CHECK,
                    initiator_kind="Admin",
                    initiator_name=interaction.user.display_name,
                    notes=summary_text,
                    duration_ms=duration_ms
                )

                await post_if_changed(self.bot, changeset)

            except Exception as e:
                logger.exception(f"Error posting leadership log: {e}")
                # Don't fail the command for logging errors

            logger.info(
                f"Bulk verification check completed by {interaction.user.id} "
                f"for {len(status_rows)} members in {duration_ms}ms"
            )

        except Exception as e:
            logger.error(f"Unexpected error in bulk verification check: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {e!s}",
                    ephemeral=True
                )
            except:
                pass  # Response might have already been sent


class VerifyBulkCog(commands.Cog):
    """Cog for bulk verification status checking."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verify_commands = VerifyCommands(bot)

    async def cog_load(self):
        """Add the command group when the cog loads."""
        self.bot.tree.add_command(self.verify_commands)
        logger.info("Verify bulk commands loaded")

    async def cog_unload(self):
        """Remove the command group when the cog unloads."""
        self.bot.tree.remove_command(self.verify_commands.name)
        logger.info("Verify bulk commands unloaded")


async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(VerifyBulkCog(bot))
