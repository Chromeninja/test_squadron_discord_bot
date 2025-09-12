"""
Legacy admin commands that were in the original admin.py.
These maintain compatibility with the original bot functionality.
"""

from datetime import datetime
from pathlib import Path

import discord
from config.config_loader import ConfigLoader
from discord import app_commands
from discord.ext import commands
from helpers.discord_api import send_message
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from helpers.permissions_helper import (
    app_command_check_configured_roles,
    resolve_role_ids_for_guild,
)
from helpers.rate_limiter import reset_all_attempts, reset_attempts
from helpers.role_helper import reverify_member
from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import flush_tasks
from helpers.token_manager import clear_all_tokens, clear_token
from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)
config = ConfigLoader.load_config()


class LegacyAdminCommands(commands.Cog):
    """Legacy admin commands for compatibility."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.BOT_ADMIN_ROLE_IDS = getattr(self.bot, "BOT_ADMIN_ROLE_IDS", [])
        if not hasattr(self.bot, "BOT_ADMIN_ROLE_IDS"):
            logger.warning(
                "BOT_ADMIN_ROLE_IDS attribute missing from bot. Defaulting to empty list."
            )
        self.LEAD_MODERATOR_ROLE_IDS = getattr(self.bot, "LEAD_MODERATOR_ROLE_IDS", [])
        if not hasattr(self.bot, "LEAD_MODERATOR_ROLE_IDS"):
            logger.warning(
                "LEAD_MODERATOR_ROLE_IDS attribute missing from bot. Defaulting to empty list."
            )
        logger.info(f"Tracking bot admin roles: {self.BOT_ADMIN_ROLE_IDS}")
        logger.info(f"Tracking lead moderator roles: {self.LEAD_MODERATOR_ROLE_IDS}")

        # Resolve configured role IDs against available guilds and log missing ones.
        try:
            if self.bot.guilds:
                resolve_role_ids_for_guild(self.bot.guilds[0])
        except Exception as e:
            logger.debug(f"Role validation failed at init: {e}")
        logger.info("Legacy Admin cog initialized.")

    @app_commands.command(
        name="reset-all", description="Reset verification timers for all members."
    )
    @app_commands.guild_only()
    @app_command_check_configured_roles(config["roles"]["bot_admins"])
    @app_commands.checks.has_any_role(*config["roles"]["bot_admins"])
    async def reset_all(self, interaction: discord.Interaction) -> None:
        """
        Reset verification timers for all members. Bot Admins only.
        """
        logger.info(f"'reset-all' command triggered by user {interaction.user.id}.")
        await reset_all_attempts()
        clear_all_tokens()
        await send_message(
            interaction, "✅ Reset verification timers for all members.", ephemeral=True
        )
        logger.info(
            "Reset-all command completed successfully.",
            extra={"user_id": interaction.user.id},
        )

    @app_commands.command(
        name="reset-user", description="Reset verification timer for a specific user."
    )
    @app_commands.describe(member="The member whose timer you want to reset.")
    @app_commands.guild_only()
    @app_command_check_configured_roles(
        config["roles"]["bot_admins"] + config["roles"]["lead_moderators"]
    )
    @app_commands.checks.has_any_role(
        *config["roles"]["bot_admins"], *config["roles"]["lead_moderators"]
    )
    async def reset_user(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """
        Reset a specific user's verification timer. Bot Admins and Lead Moderators.
        """
        logger.info(
            f"'reset-user' command triggered by user {interaction.user.id} for member {member.id}."
        )
        await reset_attempts(member.id)
        clear_token(member.id)
        await send_message(
            interaction,
            f"✅ Reset verification timer for {member.mention}.",
            ephemeral=True,
        )
        logger.info(
            "Reset-user command completed successfully.",
            extra={"user_id": interaction.user.id, "target_user_id": member.id},
        )

    @app_commands.command(name="view-logs", description="View recent bot logs.")
    @app_commands.guild_only()
    @app_command_check_configured_roles(config["roles"]["bot_admins"])
    @app_commands.checks.has_any_role(*config["roles"]["bot_admins"])
    async def view_logs(self, interaction: discord.Interaction) -> None:
        """View recent bot logs (Bot Admins only)."""
        logger.info(f"'view-logs' command triggered by user {interaction.user.id}.")

        try:
            await interaction.response.defer(ephemeral=True)

            log_file = Path("logs/bot.log")
            if not log_file.exists():
                await interaction.followup.send(
                    "❌ Log file not found.",
                    ephemeral=True
                )
                return

            # Read last 20 lines of the log file
            with open(log_file, encoding="utf-8") as f:
                lines = f.readlines()
                recent_lines = lines[-20:] if len(lines) > 20 else lines

            log_content = "".join(recent_lines)

            # Truncate if too long for Discord
            if len(log_content) > 1900:
                log_content = log_content[-1900:]
                log_content = "...\n" + log_content

            embed = discord.Embed(
                title="📋 Recent Bot Logs",
                description=f"```\n{log_content}\n```",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in view-logs command: {e}")
            await interaction.followup.send(
                f"❌ Error retrieving logs: {e!s}",
                ephemeral=True
            )

    @app_commands.command(
        name="recheck-user",
        description="Force a verification re-check for a user (Bot Admins & Lead Moderators).",
    )
    @app_command_check_configured_roles(
        config["roles"]["bot_admins"] + config["roles"].get("lead_moderators", [])
    )
    @app_commands.checks.has_any_role(
        *config["roles"]["bot_admins"], *config["roles"].get("lead_moderators", [])
    )
    @app_commands.guild_only()
    async def recheck_user(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """Force a verification re-check for a user."""
        logger.info(f"'recheck-user' command triggered by user {interaction.user.id} for member {member.id}.")

        try:
            await interaction.response.defer(ephemeral=True)

            # Fetch existing verification record
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT rsi_handle FROM verification WHERE user_id = ?",
                    (member.id,)
                )
                row = await cursor.fetchone()

            if not row:
                await interaction.followup.send(
                    f"❌ {member.mention} is not verified.",
                    ephemeral=True
                )
                return

            rsi_handle = row[0]

            # Snapshot before reverify
            before_snap = await snapshot_member_state(self.bot, member)

            # Attempt re-verification
            try:
                result = await reverify_member(self.bot, member, rsi_handle)
            except Exception as e:
                logger.error(f"Error during reverification: {e}")
                await interaction.followup.send(
                    f"❌ Error during re-verification: {e!s}",
                    ephemeral=True
                )
                return

            success, status_info, message = result
            if not success:
                await interaction.followup.send(
                    f"❌ Re-verification failed: {message}",
                    ephemeral=True
                )
                return

            # Flush task queue to apply changes
            await flush_tasks()

            # Snapshot after
            after_snap = await snapshot_member_state(self.bot, member)
            diff = diff_snapshots(before_snap, after_snap)

            # Log changes
            try:
                cs = ChangeSet(
                    user_id=member.id,
                    event=EventType.MANUAL_CHECK,
                    initiator_kind="Admin",
                    initiator_name=interaction.user.display_name,
                    notes=f"Manual recheck by {interaction.user.display_name}"
                )
                for k, v in diff.items():
                    setattr(cs, k, v)
                await post_if_changed(self.bot, cs)
            except Exception as e:
                logger.debug(f"Leadership log post failed: {e}")

            await interaction.followup.send(
                f"✅ Re-verification completed for {member.mention}. {message}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in recheck-user command: {e}")
            await interaction.followup.send(
                f"❌ Error during re-check: {e!s}",
                ephemeral=True
            )

    @reset_all.error
    @reset_user.error
    @recheck_user.error
    @view_logs.error
    async def admin_command_error(self, interaction: discord.Interaction, error) -> None:
        """Handle errors in admin commands."""
        logger.error(f"Admin command error: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Command error: {error!s}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Command error: {error!s}",
                    ephemeral=True
                )
        except discord.HTTPException:
            pass  # Ignore if we can't send error message


async def setup(bot: commands.Bot) -> None:
    logger.info("Setting up Legacy Admin Commands cog.")
    await bot.add_cog(LegacyAdminCommands(bot))
    logger.info("Legacy Admin Commands cog successfully added.")
