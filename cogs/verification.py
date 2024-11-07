# cogs/verification.py

import discord
from discord.ext import commands
import logging
import asyncio

from helpers.embeds import create_verification_embed
from helpers.views import VerificationView

class VerificationCog(commands.Cog):
    """
    Cog to handle user verification within the Discord server.
    """
    def __init__(self, bot):
        """
        Initializes the VerificationCog with the bot instance.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.verification_channel_id = bot.VERIFICATION_CHANNEL_ID
        # Create a background task for sending the verification message
        self.bot.loop.create_task(self.send_verification_message())

    async def send_verification_message(self):
        """
        Sends the initial verification message to the verification channel.
        """
        logging.info("Starting to send verification message...")
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.verification_channel_id)
        if channel is None:
            logging.error(f"Could not find the channel with ID {self.verification_channel_id}.")
            return
        else:
            logging.info(f"Found verification channel: {channel.name} (ID: {self.verification_channel_id})")

        # Clear all messages in the verification channel
        logging.info("Clearing messages in the verification channel...")
        await self.clear_verification_channel(channel)
        logging.info("Cleared messages in the verification channel.")

        # Create the verification embed
        embed = create_verification_embed()

        # Initialize the verification view with buttons
        view = VerificationView(self.bot)

        # Send the embed with the interactive view to the channel
        try:
            logging.info("Attempting to send the verification embed...")
            await channel.send(embed=embed, view=view)
            logging.info("Sent verification message in channel.")
        except Exception as e:
            logging.exception(f"Failed to send verification message: {e}")

    async def clear_verification_channel(self, channel):
        """
        Clears all messages from the specified verification channel.

        Args:
            channel (discord.TextChannel): The channel to clear messages from.
        """
        logging.info("Attempting to clear verification channel messages...")
        try:
            # Use channel.purge to delete messages
            deleted = await channel.purge(limit=None)
            logging.info(f"Deleted {len(deleted)} messages in the verification channel.")
        except discord.Forbidden:
            logging.error("Bot lacks permission to delete messages in the verification channel.")
        except discord.HTTPException as e:
            logging.exception(f"Failed to delete messages: {e}")

async def setup(bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
