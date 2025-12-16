from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from helpers.bulk_check import collect_targets
from helpers.decorators import require_permission_level
from helpers.permissions_helper import PermissionLevel
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


class VerifyCommands(app_commands.Group):
    """Verification-related admin commands."""

    def __init__(self, bot: MyBot):
        super().__init__(name="verify", description="Verification management commands")
        self.bot = bot

    @app_commands.command(
        name="check-user",
        description="Check verification status for a single user with org verification",
    )
    @app_commands.describe(
        member="Member to check",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.MODERATOR)
    async def check_user(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """
        Check verification status for a single user.

        - Displays current verification status
        - Verifies RSI org status (main and affiliate orgs)
        - No changes are made
        """
        await interaction.response.defer(ephemeral=True)

        try:
            members_list = [member]
            await self._handle_check_action(interaction, members_list)

        except Exception as e:
            logger.error(f"Unexpected error in check-user: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {e!s}", ephemeral=True
                )
            except Exception:
                pass

    @app_commands.command(
        name="check-members",
        description="Check verification status for multiple users with org verification",
    )
    @app_commands.describe(
        members="Member(s) to check (mentions or IDs)",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.MODERATOR)
    async def check_members(
        self,
        interaction: discord.Interaction,
        members: str,
    ) -> None:
        """
        Check verification status for multiple users.

        - Displays current verification status
        - Verifies RSI org status (main and affiliate orgs)
        - No changes are made
        """
        await interaction.response.defer(ephemeral=True)

        try:
            if not members or not members.strip():
                await interaction.followup.send(
                    "❌ At least one member must be specified.", ephemeral=True
                )
                return

            # Collect target members
            try:
                if not interaction.guild:
                    await interaction.followup.send(
                        "❌ This command can only be used in a server.", ephemeral=True
                    )
                    return
                members_list = await collect_targets(
                    "users", interaction.guild, members, None
                )
            except Exception as e:
                logger.exception(f"Error collecting targets: {e}")
                await interaction.followup.send(
                    f"❌ Error collecting target members: {e!s}", ephemeral=True
                )
                return

            if not members_list:
                await interaction.followup.send(
                    "❌ No valid members found. Make sure to use proper mentions or valid user IDs.\n"
                    "Example: `@user1 @user2 123456789012345678`",
                    ephemeral=True,
                )
                return

            await self._handle_check_action(interaction, members_list)

        except Exception as e:
            logger.error(f"Unexpected error in check-members: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {e!s}", ephemeral=True
                )
            except Exception:
                pass

    @app_commands.command(
        name="check-channel",
        description="Check verification status for users in a voice channel with org verification",
    )
    @app_commands.describe(
        channel="Voice channel to check",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.MODERATOR)
    async def check_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ) -> None:
        """
        Check verification status for users in a voice channel.

        - Displays current verification status
        - Verifies RSI org status (main and affiliate orgs)
        - No changes are made
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Collect target members from channel
            try:
                if not interaction.guild:
                    await interaction.followup.send(
                        "❌ This command can only be used in a server.", ephemeral=True
                    )
                    return
                members_list = await collect_targets(
                    "voice_channel", interaction.guild, None, channel
                )
            except Exception as e:
                logger.exception(f"Error collecting targets: {e}")
                await interaction.followup.send(
                    f"❌ Error collecting target members: {e!s}", ephemeral=True
                )
                return

            if not members_list:
                await interaction.followup.send(
                    f"❌ The voice channel {channel.mention} is empty.", ephemeral=True
                )
                return

            await self._handle_check_action(interaction, members_list)

        except Exception as e:
            logger.error(f"Unexpected error in check-channel: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {e!s}", ephemeral=True
                )
            except Exception:
                pass

    @app_commands.command(
        name="check-voice",
        description="Check verification status for all users in active voice channels with org verification",
    )
    @app_commands.guild_only()
    @require_permission_level(PermissionLevel.MODERATOR)
    async def check_voice(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """
        Check verification status for all users in active voice channels.

        - Displays current verification status
        - Verifies RSI org status (main and affiliate orgs)
        - No changes are made
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Collect target members from all active voice channels
            try:
                if not interaction.guild:
                    await interaction.followup.send(
                        "❌ This command can only be used in a server.", ephemeral=True
                    )
                    return
                members_list = await collect_targets(
                    "active_voice", interaction.guild, None, None
                )
            except Exception as e:
                logger.exception(f"Error collecting targets: {e}")
                await interaction.followup.send(
                    f"❌ Error collecting target members: {e!s}", ephemeral=True
                )
                return

            if not members_list:
                await interaction.followup.send(
                    "❌ No members found in any active voice channels.", ephemeral=True
                )
                return

            await self._handle_check_action(interaction, members_list)

        except Exception as e:
            logger.error(f"Unexpected error in check-voice: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {e!s}", ephemeral=True
                )
            except Exception:
                pass

    async def _handle_check_action(
        self,
        interaction: discord.Interaction,
        members: list[discord.Member],
    ) -> None:
        """Handle check action: read-only status verification with RSI org details."""
        try:
            batch_size = (
                self.bot.config.get("auto_recheck", {})
                .get("batch", {})
                .get("max_users_per_run", 50)
            )

            # Check if another job is running
            is_running = self.bot.services.verify_bulk.is_running()
            queue_size_before = self.bot.services.verify_bulk.queue_size()

            # Enqueue the manual job with RSI verification always enabled
            job_id = await self.bot.services.verify_bulk.enqueue_manual(
                interaction=interaction,
                members=members,
                scope_label="specific users",
                scope_channel=None,
                recheck_rsi=True,
            )

            # Provide immediate feedback
            if is_running:
                await interaction.followup.send(
                    f"⏳ Your verification check has been queued at position {queue_size_before + 1}. "
                    f"There's an active job running.\n"
                    f"Checking {len(members)} users (batch size: {batch_size}). "
                    f"Final results will be posted in leadership chat.",
                    ephemeral=True,
                )
            elif queue_size_before > 0:
                await interaction.followup.send(
                    f"⏳ Your verification check has been queued at position {queue_size_before + 1}.\n"
                    f"Checking {len(members)} users (batch size: {batch_size}). "
                    f"Final results will be posted in leadership chat.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"⏳ Starting verification check for {len(members)} users (batch size: {batch_size})...\n"
                    f"Final results will be posted in leadership chat.",
                    ephemeral=True,
                )

            logger.info(
                f"Enqueued bulk verification check (job {job_id}) by {interaction.user.id} "
                f"for {len(members)} members"
            )

        except Exception as e:
            logger.exception(f"Error in check action: {e}")
            await interaction.followup.send(
                f"❌ Error starting verification check: {e!s}", ephemeral=True
            )


class VerifyBulkCog(commands.Cog):
    """Cog for bulk verification status checking."""

    def __init__(self, bot: MyBot):
        self.bot = bot
        self.verify_commands = VerifyCommands(bot)

    async def cog_load(self) -> None:
        """Add the command group when the cog loads."""
        self.bot.tree.add_command(self.verify_commands)
        logger.info("Verify bulk commands loaded")

    async def cog_unload(self) -> None:
        """Remove the command group when the cog unloads."""
        self.bot.tree.remove_command(self.verify_commands.name)
        logger.info("Verify bulk commands unloaded")


async def setup(bot: commands.Bot) -> None:
    """Setup function for the cog."""
    await bot.add_cog(VerifyBulkCog(bot))  # type: ignore
