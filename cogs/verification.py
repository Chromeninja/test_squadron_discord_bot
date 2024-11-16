# cogs/verification.py

import discord
from discord.ext import commands

from helpers.embeds import create_verification_embed
from helpers.views import VerificationView
from helpers.logger import get_logger

# Initialize logger
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
        """
        logger.info("Starting to send verification message...")
        channel = self.bot.get_channel(self.bot.VERIFICATION_CHANNEL_ID)
        if channel is None:
            logger.error(f"Could not find the channel with ID {self.bot.VERIFICATION_CHANNEL_ID}.")
            return
        else:
            logger.info(f"Found verification channel: {channel.name} (ID: {self.bot.VERIFICATION_CHANNEL_ID})")

        # Delete the previous message sent by the bot in the verification channel
        logger.info("Attempting to delete previous bot message in the verification channel...")
        await self.delete_previous_bot_message(channel)
        logger.info("Deleted previous bot message in the verification channel.")

        # Create the verification embed
        embed = create_verification_embed()

        # Initialize the verification view with buttons
        view = VerificationView(self.bot)

        # Send the embed with the interactive view to the channel
        try:
            logger.info("Attempting to send the verification embed...")
            await channel.send(embed=embed, view=view)
            logger.info("Sent verification message in channel.")
        except Exception as e:
            logger.exception(f"Failed to send verification message: {e}")

    async def delete_previous_bot_message(self, channel: discord.TextChannel):
        """
        Deletes the previous message sent by the bot in the specified channel.

        Args:
            channel (discord.TextChannel): The channel to search for the bot's message.
        """
        try:
            async for message in channel.history(limit=100):
                if message.author == self.bot.user:
                    await message.delete()
                    logger.info(f"Deleted previous message from bot: Message ID {message.id}")
                    return
            logger.info("No previous bot message found to delete.")
        except discord.Forbidden:
            logger.error("Bot lacks permission to delete messages in the verification channel.")
        except discord.HTTPException as e:
            logger.exception(f"Failed to delete bot message: {e}")

async def setup(bot: commands.Bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
