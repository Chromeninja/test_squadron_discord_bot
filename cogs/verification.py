# cogs/verification.py

import discord
from discord.ext import commands
import json
import os

from helpers.database import Database
from helpers.embeds import (
    create_verification_embed,
    create_error_embed,
    create_success_embed,
    create_cooldown_embed,
    build_welcome_description,
)
from helpers.views import VerificationView
from helpers.logger import get_logger
from helpers.discord_api import followup_send_message
from helpers.role_helper import reverify_member
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.announcement import send_verification_announcements

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
        # Schedule the verification message to be sent after the bot is ready
        self.bot.loop.create_task(self.wait_and_send_verification_message())

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
        await interaction.response.defer(ephemeral=True)
        member = interaction.user

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT rsi_handle FROM verification WHERE user_id = ?",
                (member.id,)
            )
            row = await cursor.fetchone()
            if not row:
                embed = create_error_embed("You are not verified yet. Please click Verify first.")
                await followup_send_message(interaction, "", embed=embed, ephemeral=True)
                return
            rsi_handle = row[0]

        rate_limited, wait_until = await check_rate_limit(member.id, "recheck")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        result = await reverify_member(member, rsi_handle, self.bot)
        if not result[0]:
            embed = create_error_embed(result[2] or "Re-check failed. Please try again later.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        status_tuple = result[1]
        if isinstance(status_tuple, tuple):
            old_status, new_status = status_tuple
        else:
            old_status = new_status = status_tuple
        await log_attempt(member.id, "recheck")

        description = build_welcome_description(new_status)
        embed = create_success_embed(description)
        await followup_send_message(interaction, "", embed=embed, ephemeral=True)

        admin_display = getattr(interaction.user, "display_name", str(interaction.user))
        await send_verification_announcements(
            self.bot,
            member,
            old_status,
            new_status,
            is_recheck=True,
            by_admin=admin_display
        )

async def setup(bot: commands.Bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
