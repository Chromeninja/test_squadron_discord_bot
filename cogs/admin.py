# cogs/admin.py

import discord
import os
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime
from helpers.role_helper import reverify_member
from config import CONFIG

from config.config_loader import ConfigLoader

from helpers.rate_limiter import reset_attempts, reset_all_attempts
from helpers.token_manager import clear_token, clear_all_tokens
from helpers.logger import get_logger
from helpers.discord_api import send_message
from helpers.database import Database
from helpers.announcement import send_verification_announcements

# Load Config
logger = get_logger(__name__)

config = ConfigLoader.load_config()

class Admin(commands.Cog):
    """
    Admin commands for managing the bot, including restarting, resetting, etc.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.BOT_ADMIN_ROLE_IDS = self.bot.BOT_ADMIN_ROLE_IDS
        self.LEAD_MODERATOR_ROLE_IDS = self.bot.LEAD_MODERATOR_ROLE_IDS

        logger.info(f"Tracking bot admin roles: {self.BOT_ADMIN_ROLE_IDS}")
        logger.info(f"Tracking lead moderator roles: {self.LEAD_MODERATOR_ROLE_IDS}")
        logger.info("Admin cog initialized.")

    @app_commands.command(name="reset-all", description="Reset verification timers for all members.")
    @app_commands.guild_only()
    @app_commands.checks.has_any_role(*config['roles']['bot_admins'])
    async def reset_all(self, interaction: discord.Interaction):
        """
        Slash command to reset verification timers for all members.
        Accessible only by Bot Admins.
        """
        logger.info(f"'reset-all' command triggered by user {interaction.user.id}.")  # Log command trigger
        await reset_all_attempts()
        clear_all_tokens()
        await send_message(interaction, "✅ Reset verification timers for all members.", ephemeral=True)
        logger.info("Reset-all command completed successfully.", extra={'user_id': interaction.user.id})

    @app_commands.command(name="reset-user", description="Reset verification timer for a specific user.")
    @app_commands.describe(member="The member whose timer you want to reset.")
    @app_commands.guild_only()
    @app_commands.checks.has_any_role(*config['roles']['bot_admins'], *config['roles']['lead_moderators'])
    async def reset_user(self, interaction: discord.Interaction, member: discord.Member):
        """
        Slash command to reset a specific user's verification timer.
        Accessible by Bot Admins and Lead Moderators.
        """
        logger.info(f"'reset-user' command triggered by user {interaction.user.id} for member {member.id}.")  # Log command trigger
        await reset_attempts(member.id)
        clear_token(member.id)
        await send_message(interaction, f"✅ Reset verification timer for {member.mention}.", ephemeral=True)
        logger.info("Reset-user command completed successfully.", extra={
            'user_id': interaction.user.id,
            'target_user_id': member.id
        })

    @app_commands.command(name="status", description="Check the status of the bot.")
    @app_commands.guild_only()
    @app_commands.checks.has_any_role(*config['roles']['bot_admins'], *config['roles']['lead_moderators'])
    async def status(self, interaction: discord.Interaction):
        """
        Slash command to check bot status.
        Accessible by Bot Admins and Lead Moderators.
        """
        logger.info(f"'status' command triggered by user {interaction.user.id}.")  # Log command trigger
        uptime = self.bot.uptime
        await send_message(interaction, f"✅ Bot is online and operational. Uptime: {uptime}.", ephemeral=True)
        logger.info("Status command completed successfully.", extra={'user_id': interaction.user.id})

    @app_commands.command(name="view-logs", description="View recent bot logs.")
    @app_commands.guild_only()
    @app_commands.checks.has_any_role(*config['roles']['bot_admins'])
    async def view_logs(self, interaction: discord.Interaction):
        """
        Slash command to view bot logs.
        Accessible only by Bot Admins.
        """
        logger.info(f"'view-logs' command triggered by user {interaction.user.id}.")  # Log command trigger
        try:
            log_file_path = os.path.join('logs', 'bot.log')
            with open(log_file_path, "r") as log_file:
                logs = log_file.read()
            if len(logs) > 1900:
                await send_message(interaction, "ℹ️ Logs are too long to display here. Check your DM.", ephemeral=True)
                await interaction.user.send(file=discord.File(log_file_path))
            else:
                await send_message(interaction, f"```\n{logs}\n```", ephemeral=True)
            logger.info("View-logs command completed successfully.", extra={'user_id': interaction.user.id})
        except Exception as e:
            logger.exception(f"Failed to send logs: {e}", extra={'user_id': interaction.user.id})
            await send_message(interaction, "❌ Failed to retrieve logs.", ephemeral=True)

    @app_commands.command(name="recheck-user", description="Force a verification re-check for a user (Bot Admins only).")
    @app_commands.checks.has_any_role(*CONFIG['roles']['bot_admins'])
    @app_commands.guild_only()
    async def recheck_user(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT rsi_handle, membership_status, last_updated "
                "FROM verification WHERE user_id = ?",
                (member.id,)
            )
            row = await cursor.fetchone()
        if not row:
            await interaction.followup.send(
                f"{member.mention} is not verified yet.",
                ephemeral=True
            )
            return
        old_role, timestamp = row[1], row[2]
        date_str = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M UTC")
        success, status_tuple, error_msg = await reverify_member(member, row[0], self.bot)
        if not success:
            await interaction.followup.send(
                error_msg or "Re-check failed.",
                ephemeral=True
            )
            return

        # Unpack statuses
        if isinstance(status_tuple, tuple):
            old_status, new_status = status_tuple
        else:
            old_status = new_status = status_tuple

        # Announce to channels
        admin_display = interaction.user.mention

        await send_verification_announcements(
            self.bot,
            member,
            old_status,
            new_status,
            is_recheck=True,
            by_admin=admin_display
        )

        await interaction.followup.send(
            f"{member.display_name} is now {new_status} (was {old_status} on {date_str})",
            ephemeral=True
        )
        logger.info(
            "Admin %s rechecked %s in guild %s: success=%s old=%s new=%s",
            interaction.user.id,
            member.id,
            interaction.guild.id,
            success,
            old_status,
            new_status,
        )

    @reset_all.error
    @reset_user.error
    @status.error
    @recheck_user.error
    @view_logs.error
    async def admin_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingAnyRole):
            logger.warning(f"Permission error for {interaction.command.name} by user {interaction.user.id}.")
            await send_message(
                interaction,
                "❌ You don't have the required permissions to use this command.",
                ephemeral=True
            )
        elif isinstance(error, app_commands.errors.MissingPermissions):
            logger.warning(f"Missing permissions for {interaction.command.name} by user {interaction.user.id}.")
            await send_message(
                interaction,
                "❌ You lack the necessary permissions to execute this command.",
                ephemeral=True
            )
        else:
            logger.exception(f"Error in command {interaction.command.name}: {error}", extra={'user_id': interaction.user.id})
            await send_message(interaction, "An error occurred while processing the command.", ephemeral=True)

async def setup(bot: commands.Bot):
    logger.info("Setting up Admin cog.")
    await bot.add_cog(Admin(bot))
    logger.info("Admin cog successfully added.")