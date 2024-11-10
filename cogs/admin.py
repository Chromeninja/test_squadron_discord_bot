# cogs/admin.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List

from config.config_loader import ConfigLoader

# Access configuration values from config.yaml
config = ConfigLoader.load_config()


class Admin(commands.Cog):
    """
    Admin commands for managing the bot, including restarting, resetting, etc.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize role IDs as instance variables
        self.BOT_ADMIN_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('bot_admins', [])]
        self.LEAD_MODERATOR_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('lead_moderators', [])]

    async def has_roles(self, interaction: discord.Interaction, role_ids: List[int]) -> bool:
        """
        Helper method to check if a user has any of the specified role IDs.

        Args:
            interaction: The interaction object.
            role_ids: List of role IDs to check against.

        Returns:
            True if user has any of the roles, False otherwise.
        """
        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in role_ids)

    @app_commands.command(name="restart", description="Restart the bot. Only for Bot Admins.")
    async def restart(self, interaction: discord.Interaction):
        """Slash command to restart the bot."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            await interaction.response.send_message("Restarting the bot...", ephemeral=True)
            logging.info(f"Restart command issued by {interaction.user} (ID: {interaction.user.id}).")
            await self.bot.close()
        else:
            await interaction.response.send_message("You don't have permission to restart the bot.", ephemeral=True)

    @app_commands.command(name="reset-all", description="Reset verification timers for all members. Only for Bot Admins.")
    async def reset_all(self, interaction: discord.Interaction):
        """Slash command to reset verification timers for all members."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            await interaction.response.send_message("Resetting verification timers for all members...", ephemeral=True)
            logging.info(f"Reset all command issued by {interaction.user} (ID: {interaction.user.id}).")
            # Implement the reset logic here
        else:
            await interaction.response.send_message("You don't have permission to reset all members.", ephemeral=True)

    @app_commands.command(name="reset-user", description="Reset verification timer for a specific user. Bot Admins and Lead Moderators.")
    @app_commands.describe(member="The member whose timer you want to reset.")
    async def reset_user(self, interaction: discord.Interaction, member: discord.Member):
        """Slash command to reset a specific user's verification timer."""
        combined_roles = self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS
        if await self.has_roles(interaction, combined_roles):
            await interaction.response.send_message(f"Resetting verification timer for {member.mention}...", ephemeral=True)
            logging.info(f"Reset user command issued by {interaction.user} (ID: {interaction.user.id}) for {member} (ID: {member.id}).")
            # Implement the reset logic here
        else:
            await interaction.response.send_message("You don't have permission to reset this user's timer.", ephemeral=True)

    @app_commands.command(name="reload-config", description="Reload the bot's configuration. Only for Bot Admins.")
    async def reload_config(self, interaction: discord.Interaction):
        """Slash command to reload the bot's configuration."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            ConfigLoader.load_config()  # Reload the config
            # Update role IDs after reloading config
            self.BOT_ADMIN_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('bot_admins', [])]
            self.LEAD_MODERATOR_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('lead_moderators', [])]
            await interaction.response.send_message("Configuration reloaded successfully.", ephemeral=True)
            logging.info(f"Reload config command issued by {interaction.user} (ID: {interaction.user.id}).")
        else:
            await interaction.response.send_message("You don't have permission to reload the configuration.", ephemeral=True)

    @app_commands.command(name="shutdown", description="Shutdown the bot. Only for Bot Admins.")
    async def shutdown(self, interaction: discord.Interaction):
        """Slash command to shutdown the bot."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            await interaction.response.send_message("Shutting down the bot...", ephemeral=True)
            logging.info(f"Shutdown command issued by {interaction.user} (ID: {interaction.user.id}).")
            await self.bot.close()
        else:
            await interaction.response.send_message("You don't have permission to shut down the bot.", ephemeral=True)

    @app_commands.command(name="status", description="Check the status of the bot.")
    async def status(self, interaction: discord.Interaction):
        """Slash command to check bot status."""
        combined_roles = self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS
        if await self.has_roles(interaction, combined_roles):
            uptime = self.bot.uptime
            status_message = f"Bot is online and operational. Uptime: {uptime}."
            await interaction.response.send_message(status_message, ephemeral=True)
            logging.info(f"Status command issued by {interaction.user} (ID: {interaction.user.id}).")
        else:
            await interaction.response.send_message("You don't have permission to check the bot's status.", ephemeral=True)

    @app_commands.command(name="view-logs", description="View recent bot logs. Bot Admins and Lead Moderators.")
    async def view_logs(self, interaction: discord.Interaction):
        """Slash command to view bot logs."""
        combined_roles = self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS
        if await self.has_roles(interaction, combined_roles):
            try:
                with open("bot.log", "r") as log_file:
                    logs = log_file.read()
                if len(logs) > 2000:
                    await interaction.response.send_message("Logs are too long to display here. Check your DM.", ephemeral=True)
                    await interaction.user.send(file=discord.File("bot.log"))
                else:
                    await interaction.response.send_message(f"```\n{logs}\n```", ephemeral=True)
                logging.info(f"View logs command issued by {interaction.user} (ID: {interaction.user.id}).")
            except Exception as e:
                logging.exception(f"Failed to send logs to {interaction.user} (ID: {interaction.user.id}): {e}")
                await interaction.response.send_message("Failed to retrieve logs.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have permission to view the logs.", ephemeral=True)

    # Error handling for permissions and other issues
    @restart.error
    @reset_all.error
    @reset_user.error
    @reload_config.error
    @shutdown.error
    @status.error
    @view_logs.error
    async def admin_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingAnyRole):
            await interaction.response.send_message("You don't have the required permissions to use this command.", ephemeral=True)
        else:
            logging.exception(f"Error in command {interaction.command.name}: {error}")
            await interaction.response.send_message("An error occurred while processing the command.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
