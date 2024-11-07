# helpers/modals.py

import discord
from discord.ui import Modal, TextInput
import logging

from helpers.embeds import create_error_embed, create_success_embed, create_cooldown_embed
from helpers.rate_limiter import log_attempt, get_remaining_attempts, check_rate_limit, reset_attempts
from helpers.token_manager import token_store, validate_token, clear_token
from verification.rsi_verification import is_valid_rsi_handle, is_valid_rsi_bio
from helpers.role_helper import assign_roles

class HandleModal(Modal, title="Verification"):
    """
    Modal to collect the user's RSI handle for verification.
    """
    rsi_handle = TextInput(
        label="RSI Handle",
        placeholder="Enter your Star Citizen handle here",
        max_length=32
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
        logging.info(f"Verification modal submitted by user {interaction.user} (ID: {interaction.user.id})")
        member = interaction.user
        rsi_handle_input = self.rsi_handle.value.strip()

        # Normalize the RSI handle to lowercase for case-insensitive handling
        rsi_handle_value = rsi_handle_input.lower()

        # Check if the user has an active token
        user_token_info = token_store.get(member.id)
        if not user_token_info:
            embed = create_error_embed(
                "No active token found. Please click 'Get Token' to receive a new token."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logging.warning(f"User {member} attempted verification without a token.")
            return

        valid, message = validate_token(member.id, user_token_info['token'])
        if not valid:
            embed = create_error_embed(message)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logging.warning(f"User {member} provided an invalid or expired token.")
            return

        # Defer the response as verification may take some time
        await interaction.response.defer(ephemeral=True)
        logging.info(f"Deferred response for user {member} during verification.")

        token = user_token_info['token']

        # Perform RSI verification with normalized handle
        verify_value = await is_valid_rsi_handle(rsi_handle_value)
        token_verify = await is_valid_rsi_bio(rsi_handle_value, token)

        # Log the attempt
        log_attempt(member.id)

        if not verify_value or not token_verify:
            # Verification failed
            remaining_attempts = get_remaining_attempts(member.id)
            if remaining_attempts <= 0:
                # User has exceeded max attempts
                _, wait_until = check_rate_limit(member.id)

                # Create and send the cooldown embed
                embed = create_cooldown_embed(wait_until)

                await interaction.followup.send(embed=embed, ephemeral=True)
                logging.info(f"User {member} exceeded verification attempts. Cooldown enforced.")
                return
            else:
                # Prepare error details with enhanced instructions
                error_details = []
                if not verify_value:
                    error_details.append("- Could not verify RSI organization membership.")
                if not token_verify:
                    error_details.append("- Token not found or does not match in RSI bio.")
                # Add additional instructions and link
                error_details.append(
                    "- Please ensure your RSI Handle is correct and check the spelling.\n"
                    "- You can find your RSI Handle on your [RSI Account Settings](https://robertsspaceindustries.com/account/settings) page, next to the handle field."
                )
                error_details.append(f"You have {remaining_attempts} attempt(s) remaining before cooldown.")
                error_message = "\n".join(error_details)
                embed = create_error_embed(error_message)
                await interaction.followup.send(embed=embed, ephemeral=True)
                logging.info(f"User {member} failed verification. Remaining attempts: {remaining_attempts}.")
                return

        # Verification successful
        assigned_role_type = await assign_roles(member, verify_value, rsi_handle_value, self.bot)
        clear_token(member.id)
        reset_attempts(member.id)  # Reset attempts on success

        # Send customized success message based on role
        if assigned_role_type == 'main':
            description = (
                "Thank you for being a main member of **TEST Squadron - Best Squadron!** "
                "We're thrilled to have you with us."
            )
        elif assigned_role_type == 'affiliate':
            description = (
                "Thanks for being an affiliate of **TEST Squadron - Best Squadron!** "
                "Consider setting **TEST** as your Main Org to share in the glory of TEST.\n\n"
                "**Instructions:**\n"
                ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
                "1️⃣ Click on **Set as Main** next to **TEST**."
            )
        elif assigned_role_type == 'non_member':
            description = (
                "Welcome! It looks like you're not a member of **TEST Squadron - Best Squadron!** "
                "Join us to be part of the adventure!\n\n"
                "🔗 [Join TEST Squadron](https://robertsspaceindustries.com/orgs/TEST)\n"
                "*Click **Enlist Now!**. Test membership requests are usually approved within 24-72 hours.*"
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
            logging.info(f"User {member} successfully verified and roles assigned as '{assigned_role_type}'.")
        except Exception as e:
            logging.exception(f"Failed to send verification success message to user {member}: {e}")
