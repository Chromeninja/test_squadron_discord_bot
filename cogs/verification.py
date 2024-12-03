# cogs/verification.py

import discord
from discord.ext import commands
import json
import os

from helpers.embeds import create_verification_embed
from helpers.views import VerificationView
from helpers.logger import get_logger

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

async def setup(bot: commands.Bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
