# helpers/modals.py

import discord
from discord.ui import Modal, TextInput
import re
from helpers.embeds import create_error_embed, create_success_embed, create_cooldown_embed
from helpers.rate_limiter import log_attempt, get_remaining_attempts, check_rate_limit, reset_attempts
from helpers.token_manager import token_store, validate_token, clear_token
from verification.rsi_verification import is_valid_rsi_handle, is_valid_rsi_bio
from helpers.role_helper import assign_roles
from helpers.database import Database
from helpers.logger import get_logger
from helpers.voice_utils import get_user_channel, update_channel_settings, safe_edit_channel, safe_delete_channel

# Initialize logger
logger = get_logger(__name__)

# Regular expression to validate RSI handle format
RSI_HANDLE_REGEX = re.compile(r'^[A-Za-z0-9_]{1,60}$')

class HandleModal(Modal, title="Verification"):
    """
    Modal to collect the user's RSI handle for verification.
    """
    rsi_handle = TextInput(
        label="RSI Handle",
        placeholder="Enter your Star Citizen handle here",
        max_length=60
    )

    def __init__(self, bot):
        """
        Initializes the HandleModal with the bot instance.

        Args:
            bot (commands.Bot): The bot instance.
        """
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        """
        Handles the submission of the verification modal.

        Args:
            interaction (discord.Interaction): The interaction triggered by the modal submission.
        """
        member = interaction.user
        rsi_handle_input = self.rsi_handle.value.strip()

        # Validate RSI handle format
        if not RSI_HANDLE_REGEX.match(rsi_handle_input):
            embed = create_error_embed(
                "Invalid RSI Handle format. Please use only letters, numbers, and underscores, up to 60 characters."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.warning("Invalid RSI handle format provided.", extra={
                'user_id': member.id,
                'rsi_handle': rsi_handle_input
            })
            return

        # Proceed with verification to get verify_value and cased_handle
        verify_value, cased_handle = await is_valid_rsi_handle(rsi_handle_input, self.bot.http_client)
        if verify_value is None or cased_handle is None:
            embed = create_error_embed("Failed to verify RSI handle. Please check your handle and try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.warning("Verification failed: invalid RSI handle.", extra={'user_id': member.id})
            return

        # Validate token
        user_token_info = token_store.get(member.id)
        if not user_token_info:
            embed = create_error_embed(
                "No active token found. Please click 'Get Token' to receive a new token."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.warning("Verification attempted without a token.", extra={'user_id': member.id})
            return

        valid, message = validate_token(member.id, user_token_info['token'])
        if not valid:
            embed = create_error_embed(message)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.warning("Invalid or expired token provided.", extra={'user_id': member.id})
            return

        # Defer the response as verification may take some time
        await interaction.response.defer(ephemeral=True)
        logger.debug("Deferred response during verification.", extra={'user_id': member.id})

        token = user_token_info['token']

        # Perform RSI verification with sanitized handle
        verify_value_check, _ = await is_valid_rsi_handle(cased_handle, self.bot.http_client)
        if verify_value_check is None:
            embed = create_error_embed("Failed to verify RSI handle. Please check your handle and try again.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.warning("Verification failed: invalid RSI handle.", extra={'user_id': member.id})
            return

        token_verify = await is_valid_rsi_bio(cased_handle, token, self.bot.http_client)
        if token_verify is None:
            embed = create_error_embed("Failed to verify token in RSI bio. Please ensure your token is in your bio.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.warning("Verification failed: token not found in bio.", extra={'user_id': member.id})
            return

        log_attempt(member.id)

        # Check if verification failed
        if verify_value_check is None or not token_verify:
            remaining_attempts = get_remaining_attempts(member.id)
            if remaining_attempts <= 0:
                # User has exceeded max attempts
                _, wait_until = check_rate_limit(member.id)

                # Create and send the cooldown embed
                embed = create_cooldown_embed(wait_until)

                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info("User exceeded verification attempts. Cooldown enforced.", extra={'user_id': member.id})
                return
            else:
                # Prepare error details with enhanced instructions
                error_details = []
                if verify_value_check is None:
                    error_details.append("- Could not verify RSI organization membership.")
                if not token_verify:
                    error_details.append("- Token not found or does not match in RSI bio.")
                error_details.append(f"You have {remaining_attempts} attempt(s) remaining before cooldown.")
                error_message = "\n".join(error_details)
                embed = create_error_embed(error_message)
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info("User failed verification.", extra={
                    'user_id': member.id,
                    'remaining_attempts': remaining_attempts
                })
                return

        # Verification successful
        assigned_role_type = await assign_roles(member, verify_value_check, cased_handle, self.bot)
        clear_token(member.id)
        reset_attempts(member.id)  # Reset attempts on success

        # Send customized success message based on role
        if assigned_role_type == 'main':
            description = (
                "<:testSquad:1308586340996349952> **Welcome, to TEST Squadron - Best Squadron!** <:BESTSquad:1308586367303028756>\n\n"
                "We're thrilled to have you as a MAIN member of **TEST Squadron!**\n\n"
                "Join our voice chats, explore events, and engage in our text channels to make the most of your experience!\n\n"
                "Fly safe! <:o7:1306961462215970836>"
            )
        elif assigned_role_type == 'affiliate':
            description = (
                "<:testSquad:1308586340996349952> **Welcome, to TEST Squadron - Best Squadron!** <:BESTSquad:1308586367303028756>\n\n"
                "Your support helps us grow and excel. We encourage you to set **TEST** as your MAIN Org to show your loyalty.\n\n"
                "**Instructions:**\n"
                ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
                "1️⃣ Click **Set as Main** next to **TEST Squadron**.\n\n"
                "Join our voice chats, explore events, and engage in our text channels to get involved!\n\n"
                "<:o7:1306961462215970836>"
            )
        elif assigned_role_type == 'non_member':
            description = (
                "<:testSquad:1308586340996349952> **Welcome, to TEST Squadron - Best Squadron!** <:BESTSquad:1308586367303028756>\n\n"
                "It looks like you're not yet a member of our org. <:what:1306961532080623676>\n\n"
                "Join us for thrilling adventures and be part of the best and biggest community!\n\n"
                "🔗 [Join TEST Squadron](https://robertsspaceindustries.com/orgs/TEST)\n"
                "*Click **Enlist Now!**. Test membership requests are usually approved within 24-72 hours. You will need to reverify to update your roles once approved.*\n\n"
                "Join our voice chats, explore events, and engage in our text channels to get involved! <:o7:1306961462215970836>"
            )
        else:
            description = (
                "Welcome to the server! You can verify again after 3 hours if needed."
            )

        embed = create_success_embed(description)

        try:
            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )
            logger.info("User successfully verified.", extra={
                'user_id': member.id,
                'rsi_handle': cased_handle,
                'assigned_role': assigned_role_type
            })
        except Exception as e:
            logger.exception(f"Failed to send verification success message: {e}", extra={'user_id': member.id})

class CloseChannelConfirmationModal(Modal):
    """
    Modal to confirm closing the voice channel.
    """
    def __init__(self, bot):
        super().__init__(title="Confirm Close Channel")
        self.bot = bot
        self.confirmation = TextInput(
            label="Type 'CLOSE' to confirm",
            placeholder="Type 'CLOSE' to confirm",
            required=True,
            max_length=5
        )
        self.add_item(self.confirmation)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        if self.confirmation.value.strip().upper() == "CLOSE":
            # Delete the channel with rate limiting
            try:
                await safe_delete_channel(channel)
                async with Database.get_connection() as db:
                    await db.execute("DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (channel.id,))
                    await db.commit()
                await interaction.response.send_message("Your voice channel has been closed.", ephemeral=True)
                logger.info(f"{member.display_name} closed their voice channel.")
            except Exception as e:
                logger.exception(f"Error deleting voice channel: {e}")
                await interaction.response.send_message("Failed to close your voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("Channel closure cancelled.", ephemeral=True)

class ResetSettingsConfirmationModal(Modal):
    """
    Modal to confirm resetting channel settings.
    """
    def __init__(self, bot):
        super().__init__(title="Reset Channel Settings")
        self.bot = bot
        self.confirm = TextInput(
            label="Type 'RESET' to confirm",
            placeholder="RESET",
            required=True,
            min_length=5,
            max_length=5
        )
        self.add_item(self.confirm)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        # Defer the response to acknowledge the interaction
        await interaction.response.defer(ephemeral=True)

        confirmation_text = self.confirm.value.strip().upper()
        if confirmation_text != "RESET":
            await interaction.followup.send("Confirmation text does not match. Channel settings were not reset.", ephemeral=True)
            logger.info(f"{member.display_name} failed to confirm channel reset.")
            return

        try:
            # Access the Voice cog to reset channel settings
            voice_cog = self.bot.get_cog("voice")
            if not voice_cog:
                await interaction.followup.send("Voice cog is not loaded.", ephemeral=True)
                logger.error("Voice cog not found.")
                return

            # Reset the channel settings
            await voice_cog._reset_current_channel_settings(member)

            await interaction.followup.send("Your channel settings have been reset to default.", ephemeral=True)
            logger.info(f"{member.display_name} reset their channel settings.")
        except Exception as e:
            logger.exception(f"Failed to reset channel settings for {member.display_name}: {e}")
            await interaction.followup.send("An error occurred while resetting your channel settings. Please try again later.", ephemeral=True)

class NameModal(Modal):
    """
    Modal to change the voice channel name.
    """
    def __init__(self, bot):
        super().__init__(title="Change Channel Name")
        self.bot = bot
        self.channel_name = TextInput(
            label="New Channel Name",
            placeholder="Enter a new name for your channel",
            min_length=2,
            max_length=32
        )
        self.add_item(self.channel_name)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        new_name = self.channel_name.value.strip()
        if not (2 <= len(new_name) <= 32):
            await interaction.response.send_message("Channel name must be between 2 and 32 characters.", ephemeral=True)
            return
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        try:
            # Use the helper function to get the user's channel
            channel = await get_user_channel(self.bot, member)
            if not channel:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return

            # Change the channel name with rate limiting
            await safe_edit_channel(channel, name=new_name)

            # Update settings using the helper function
            await update_channel_settings(member.id, channel_name=new_name)

            await interaction.response.send_message(f"Channel name has been changed to '{new_name}'.", ephemeral=True)
            logger.info(f"{member.display_name} changed channel name to '{new_name}'.")
        except discord.Forbidden:
            logger.warning(f"Insufficient permissions to change channel name for {member.display_name}.")
            await interaction.response.send_message("I don't have permission to change the channel name.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to change channel name for {member.display_name}: {e}")
            await interaction.response.send_message("An unexpected error occurred. Please try again later.", ephemeral=True)

class LimitModal(Modal):
    """
    Modal to set the user limit for the voice channel.
    """
    def __init__(self, bot):
        super().__init__(title="Set User Limit")
        self.bot = bot
        self.user_limit = TextInput(
            label="User Limit",
            placeholder="Enter a number between 2 and 99",
            required=True,
            max_length=2
        )
        self.add_item(self.user_limit)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        try:
            limit = int(self.user_limit.value.strip())
            if not (2 <= limit <= 99):
                raise ValueError
        except ValueError:
            embed = create_error_embed("User limit must be a number between 2 and 99.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Update user limit
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        try:
            await safe_edit_channel(channel, user_limit=limit)

            # Update settings using the helper function
            await update_channel_settings(member.id, user_limit=limit)

            embed = create_success_embed(f"User limit has been set to {limit}.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"{member.display_name} set their channel user limit to {limit}.")
        except discord.Forbidden:
            logger.warning(f"Insufficient permissions to set user limit for {member.display_name}.")
            embed = create_error_embed("I don't have permission to set the user limit.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to set user limit: {e}")
            embed = create_error_embed("Failed to set user limit. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
