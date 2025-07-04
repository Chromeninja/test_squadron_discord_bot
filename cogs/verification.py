# cogs/verification.py

import discord
from discord.ext import commands
import json
import os
import time
from aiolimiter import AsyncLimiter

from helpers.embeds import (
    create_verification_embed,
    create_error_embed,
    create_success_embed,
    create_cooldown_embed,
)
from helpers.views import VerificationView
from helpers.logger import get_logger
from helpers.database import Database
from helpers.role_helper import reverify_member, get_welcome_description
from helpers.discord_api import followup_send_message
from config.config_loader import ConfigLoader
from verification.rsi_verification import lookup_rsi_user

logger = get_logger(__name__)

class VerificationCog(commands.Cog):
    """
    Cog to handle user verification within the Discord server.
    """
    def __init__(self, bot: commands.Bot):
        """
        Initializes the VerificationCog with the bot instance.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.recheck_cooldown = self.config.get('verification', {}).get('recheck_cooldown_seconds', 300)
        self.rsi_limiter = AsyncLimiter(1, 1)
        # Schedule the verification message to be sent after the bot is ready
        self.bot.loop.create_task(self.wait_and_send_verification_message())

    async def cog_load(self):
        """Register the persistent verification view when the cog loads."""
        self.bot.add_view(VerificationView(self.bot))

    async def wait_and_send_verification_message(self):
        """
        Waits until the bot is ready and sends the verification message.
        """
        await self.bot.wait_until_ready()
        await self.send_verification_message()

    async def send_verification_message(self):
        """
        Sends the initial verification message to the verification channel.
        If a message already exists, it will not send a new one.
        """
        logger.info("Starting to send verification message...")
        channel = self.bot.get_channel(self.bot.VERIFICATION_CHANNEL_ID)
        if channel is None:
            logger.error(f"Could not find the channel with ID {self.bot.VERIFICATION_CHANNEL_ID}.")
            return
        else:
            logger.info(f"Found verification channel: {channel.name} (ID: {self.bot.VERIFICATION_CHANNEL_ID})")

        # Load the message ID from a file
        message_id = None
        message_id_file = 'verification_message_id.json'
        if os.path.exists(message_id_file):
            with open(message_id_file, 'r') as f:
                data = json.load(f)
                message_id = data.get('message_id')

        if message_id:
            try:
                # Try to fetch the message
                verification_message = await channel.fetch_message(message_id)
                logger.info(f"Verification message already exists with ID: {message_id}")
                return  # Message already exists, no need to send a new one
            except discord.NotFound:
                logger.info("Verification message not found, will send a new one.")
            except Exception as e:
                logger.error(f"Error fetching verification message: {e}")

        # Create the verification embed
        embed = create_verification_embed()

        # Initialize the verification view with buttons
        view = VerificationView(self.bot)

        # Send the embed with the interactive view to the channel
        try:
            logger.info("Attempting to send the verification embed...")
            sent_message = await channel.send(embed=embed, view=view)
            logger.info(f"Sent verification message in channel. Message ID: {sent_message.id}")

            # Save the message ID to the file
            with open(message_id_file, 'w') as f:
                json.dump({'message_id': sent_message.id}, f)

        except discord.Forbidden:
            logger.error("Bot lacks permission to send messages in the verification channel.")
        except discord.HTTPException as e:
            logger.exception(f"Failed to send verification message: {e}")

    async def recheck_button(self, interaction: discord.Interaction):
        """Handle the Re-Check button interaction."""
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT rsi_handle, last_recheck FROM verification WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()

        if not row:
            embed = create_error_embed("You are not verified yet.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        rsi_handle, last_recheck = row
        now = int(time.time())
        if last_recheck and now - last_recheck < self.recheck_cooldown:
            wait_until = last_recheck + self.recheck_cooldown
            embed = create_cooldown_embed(wait_until)
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE verification SET last_recheck = ? WHERE user_id = ?",
                (now, user_id),
            )
            await db.commit()

        async with self.rsi_limiter:
            verify_value, cased_handle = await lookup_rsi_user(rsi_handle, self.bot.http_client)

        if verify_value is None or cased_handle is None:
            embed = create_error_embed("Failed to look up your RSI status. Please try again later.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        assigned_role_type = await reverify_member(interaction.user, verify_value, cased_handle, self.bot)
        description = get_welcome_description(assigned_role_type)
        embed = create_success_embed(description)
        await followup_send_message(interaction, "", embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
