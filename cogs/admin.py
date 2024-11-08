# cogs/admin.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import subprocess

from config.config_loader import ConfigLoader  # Import the ConfigLoader

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

    # Helper method to check if a user has any of the specified role IDs
    async def has_roles(self, interaction: discord.Interaction, role_ids: list) -> bool:
        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in role_ids)

    # Restart the bot
    @app_commands.command(name="restart", description="Restart the bot. Only for Bot Admins.")
    async def restart(self, interaction: discord.Interaction):
        """Slash command to restart the bot."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            await interaction.response.send_message("Restarting the bot...", ephemeral=True)
            logging.info(f"Restart command issued by {interaction.user}.")
            await self.bot.close()
            # Note: Restarting the bot requires an external process manager like PM2 or systemd
        else:
            await interaction.response.send_message("You don't have permission to restart the bot.", ephemeral=True)

    # Reset all verification timers
    @app_commands.command(name="reset-all", description="Reset verification timers for all members. Only for Bot Admins.")
    async def reset_all(self, interaction: discord.Interaction):
        """Slash command to reset verification timers for all members."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            await interaction.response.send_message("Resetting verification timers for all members...", ephemeral=True)
            logging.info(f"Reset all command issued by {interaction.user}.")
            # Implement the reset logic here
            # Example: Clear relevant data structures or database entries
        else:
            await interaction.response.send_message("You don't have permission to reset all members.", ephemeral=True)

    # Reset a specific user's verification timer
    @app_commands.command(name="reset-user", description="Reset verification timer for a specific user. Bot Admins and Lead Moderators.")
    @app_commands.describe(member="The member whose timer you want to reset.")
    async def reset_user(self, interaction: discord.Interaction, member: discord.Member):
        """Slash command to reset a specific user's verification timer."""
        combined_roles = self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS
        if await self.has_roles(interaction, combined_roles):
            await interaction.response.send_message(f"Resetting verification timer for {member.mention}...", ephemeral=True)
            logging.info(f"Reset user command issued by {interaction.user} for {member}.")
            # Implement the reset logic here
            # Example: Reset the member's attempt count in your rate limiter
        else:
            await interaction.response.send_message("You don't have permission to reset this user's timer.", ephemeral=True)

    # Reload the bot's configuration
    @app_commands.command(name="reload-config", description="Reload the bot's configuration. Only for Bot Admins.")
    async def reload_config(self, interaction: discord.Interaction):
        """Slash command to reload the bot's configuration."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            config = ConfigLoader.load_config()  # Reload the config
            # Update role IDs after reloading config
            self.BOT_ADMIN_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('bot_admins', [])]
            self.LEAD_MODERATOR_ROLE_IDS = [int(role_id) for role_id in config['roles'].get('lead_moderators', [])]
            await interaction.response.send_message("Configuration reloaded successfully.", ephemeral=True)
            logging.info(f"Reload config command issued by {interaction.user}.")
        else:
            await interaction.response.send_message("You don't have permission to reload the configuration.", ephemeral=True)

    # Shutdown the bot
    @app_commands.command(name="shutdown", description="Shutdown the bot. Only for Bot Admins.")
    async def shutdown(self, interaction: discord.Interaction):
        """Slash command to shutdown the bot."""
        if await self.has_roles(interaction, self.BOT_ADMIN_ROLE_IDS):
            await interaction.response.send_message("Shutting down the bot...", ephemeral=True)
            logging.info(f"Shutdown command issued by {interaction.user}.")
            await self.bot.close()
        else:
            await interaction.response.send_message("You don't have permission to shut down the bot.", ephemeral=True)

    # Get bot status
    @app_commands.command(name="status", description="Check the status of the bot.")
    async def status(self, interaction: discord.Interaction):
        """Slash command to check bot status."""
        combined_roles = self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS
        if await self.has_roles(interaction, combined_roles):
            uptime = self.bot.uptime
            status_message = f"Bot is online and operational. Uptime: {uptime}."
            await interaction.response.send_message(status_message, ephemeral=True)
            logging.info(f"Status command issued by {interaction.user}.")
        else:
            await interaction.response.send_message("You don't have permission to check the bot's status.", ephemeral=True)

    # View bot logs
    @app_commands.command(name="view-logs", description="View recent bot logs. Bot Admins and Lead Moderators.")
    async def view_logs(self, interaction: discord.Interaction):
        """Slash command to view bot logs."""
        combined_roles = self.BOT_ADMIN_ROLE_IDS + self.LEAD_MODERATOR_ROLE_IDS
        if await self.has_roles(interaction, combined_roles):
            try:
                with open("bot.log", "r") as log_file:
                    logs = log_file.read()
                if len(logs) > 2000:
                    # Discord messages have a 2000 character limit
                    # Send as a file instead
                    await interaction.response.send_message("Logs are too long to display here. Check your DM.", ephemeral=True)
                    await interaction.user.send(file=discord.File("bot.log"))
                else:
                    await interaction.response.send_message(f"```\n{logs}\n```", ephemeral=True)
                logging.info(f"View logs command issued by {interaction.user}.")
            except Exception as e:
                logging.error(f"Failed to send logs: {e}")
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
            logging.error(f"Error in command {interaction.command}: {error}")
            await interaction.response.send_message("An error occurred while processing the command.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
