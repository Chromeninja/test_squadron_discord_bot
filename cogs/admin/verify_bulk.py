# cogs/admin/verify_bulk.py

import discord
from discord import app_commands
from discord.ext import commands

from helpers.bulk_check import collect_targets
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
        channel="Voice channel to check (required for 'voice_channel' mode)"
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
        channel: discord.VoiceChannel | None = None
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

            # Enqueue job via verification bulk service
            try:
                batch_size = self.bot.config.get("auto_recheck", {}).get("batch", {}).get("max_users_per_run", 50)
                
                # Check if another job is running
                is_running = self.bot.services.verify_bulk.is_running()
                queue_size_before = self.bot.services.verify_bulk.queue_size()
                
                # Determine scope label and channel
                scope_label = targets.name  # "specific users", "voice channel", or "all active voice"
                scope_channel = f"#{channel.name}" if channel else None
                
                # Enqueue the manual job
                job_id = await self.bot.services.verify_bulk.enqueue_manual(
                    interaction=interaction,
                    members=members,
                    scope_label=scope_label,
                    scope_channel=scope_channel
                )
                
                # Provide immediate feedback
                if is_running:
                    await interaction.followup.send(
                        f"⏳ Your verification check has been queued at position {queue_size_before + 1}. "
                        f"There's an active job running.\n"
                        f"Checking {len(members)} users (batch size: {batch_size}). "
                        f"Final results will be posted in leadership chat.",
                        ephemeral=True
                    )
                elif queue_size_before > 0:
                    await interaction.followup.send(
                        f"⏳ Your verification check has been queued at position {queue_size_before + 1}.\n"
                        f"Checking {len(members)} users (batch size: {batch_size}). "
                        f"Final results will be posted in leadership chat.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"⏳ Starting verification check for {len(members)} users (batch size: {batch_size})...\n"
                        f"Final results will be posted in leadership chat.",
                        ephemeral=True
                    )
                
                logger.info(
                    f"Enqueued bulk verification check (job {job_id}) by {interaction.user.id} "
                    f"for {len(members)} members"
                )
                return
            
            except Exception as e:
                logger.exception(f"Error enqueueing bulk verification job: {e}")
                await interaction.followup.send(
                    f"❌ Error starting verification check: {e!s}",
                    ephemeral=True
                )
                return

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
