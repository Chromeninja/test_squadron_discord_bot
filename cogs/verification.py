# Cogs/verification.py

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
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.username_404 import handle_username_404
from helpers.leadership_log import EventType

# Import the verification repository
import importlib.util
import os as path_os
current_dir = path_os.path.dirname(path_os.path.abspath(__file__))
repo_path = path_os.path.join(path_os.path.dirname(current_dir), "bot", "app", "repositories", "verification_repo.py")
spec = importlib.util.spec_from_file_location("verification_repo", repo_path)
verification_repo_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification_repo_module)
VerificationRepository = verification_repo_module.VerificationRepository

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
            logger.error(
                f"Could not find the channel with ID {self.bot.VERIFICATION_CHANNEL_ID}."
            )
            return
        logger.info(
            f"Found verification channel: {channel.name} (ID: {self.bot.VERIFICATION_CHANNEL_ID})"
        )

        # Get guild ID (assuming single guild for now, but storing explicitly for future multi-guild support)
        guild_id = channel.guild.id if channel.guild else 0

        # Check for backward compatibility migration from JSON file
        await self._migrate_from_json_if_needed(guild_id)

        # Load the message ID from the database
        message_id = await VerificationRepository.get_verification_message_id(guild_id)

        if message_id:
            try:
                # Try to fetch the message
                await channel.fetch_message(message_id)
                logger.info(
                    f"Verification message already exists with ID: {message_id}"
                )
                return  # Message already exists, no need to send a new one
            except discord.NotFound:
                logger.info("Verification message not found, will send a new one.")
                # Remove the stale message ID from the database
                await VerificationRepository.delete_verification_message_id(guild_id)
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
            logger.info(
                f"Sent verification message in channel. Message ID: {sent_message.id}"
            )

            # Save the message ID to the database
            await VerificationRepository.set_verification_message_id(guild_id, sent_message.id)

        except discord.Forbidden:
            logger.error(
                "Bot lacks permission to send messages in the verification channel."
            )
        except discord.HTTPException as e:
            logger.exception(f"Failed to send verification message: {e}")

    async def _migrate_from_json_if_needed(self, guild_id: int):
        """
        One-time migration from JSON file to database.
        If verification_message_id.json exists, import it and delete the file.
        """
        message_id_file = "verification_message_id.json"
        if os.path.exists(message_id_file):
            try:
                logger.info("Found legacy verification_message_id.json file, migrating to database...")
                
                with open(message_id_file, "r") as f:
                    data = json.load(f)
                    message_id = data.get("message_id")
                
                if message_id:
                    # Store in database
                    await VerificationRepository.set_verification_message_id(guild_id, message_id)
                    logger.info(f"Migrated verification message ID {message_id} to database for guild {guild_id}")
                
                # Delete the JSON file
                os.remove(message_id_file)
                logger.info("Successfully migrated and removed legacy verification_message_id.json file")
                
            except Exception as e:
                logger.error(f"Failed to migrate verification_message_id.json: {e}")
                # Don't raise - we can continue without the migration

    async def recheck_button(self, interaction: discord.Interaction):
        """Handle a user-initiated recheck via the verification view button."""
        await interaction.response.defer(ephemeral=True)
        member = interaction.user

        # Fetch existing verification record
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT rsi_handle FROM verification WHERE user_id = ?", (member.id,)
            )
            row = await cursor.fetchone()
            if not row:
                embed = create_error_embed(
                    "You are not verified yet. Please click Verify first."
                )
                await followup_send_message(interaction, "", embed=embed, ephemeral=True)
                return
            rsi_handle = row[0]

        # Rate limit check
        rate_limited, wait_until = await check_rate_limit(member.id, "recheck")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Use VerificationService for verification workflow
        from bot.app.services.verification_service import VerificationService
        
        leadership_log_service = getattr(self.bot, 'leadership_log_service', None)
        announcement_service = getattr(self.bot, 'announcement_service', None)
        verification_service = VerificationService(
            leadership_log_service=leadership_log_service,
            announcement_service=announcement_service
        )
        result = await verification_service.verify_user(
            guild=member.guild,
            member=member,
            rsi_handle=rsi_handle,
            bot=self.bot,
            event_type=EventType.RECHECK,
            initiator_kind='User'
        )

        if result.handle_404:
            # Handle RSI handle not found - invoke unified remediation
            try:
                await handle_username_404(self.bot, member, rsi_handle)
            except Exception as e:  # pragma: no cover - best effort logging
                logger.warning(f"Unified 404 handler failed (button): {e}")
            verification_channel_id = getattr(self.bot, "VERIFICATION_CHANNEL_ID", 0)
            embed = create_error_embed(
                f"Your RSI Handle appears to have changed. Please re-verify in <#{verification_channel_id}>."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        if not result.success:
            embed = create_error_embed(result.message or "Re-check failed. Please try again later.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Log successful attempt
        await log_attempt(member.id, "recheck")

        # Determine status for response
        if isinstance(result.status_info, tuple):
            _old_status, new_status = result.status_info
        else:
            new_status = result.status_info

        description = build_welcome_description(new_status)
        embed = create_success_embed(description)
        await followup_send_message(interaction, "", embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
