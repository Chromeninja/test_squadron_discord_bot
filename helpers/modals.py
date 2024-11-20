# helpers/modals.py

import discord
from discord.ui import Modal, TextInput
import re

from helpers.embeds import create_error_embed, create_success_embed, create_cooldown_embed
from helpers.rate_limiter import log_attempt, get_remaining_attempts, check_rate_limit, reset_attempts
from helpers.token_manager import token_store, validate_token, clear_token
from verification.rsi_verification import is_valid_rsi_handle, is_valid_rsi_bio
from helpers.role_helper import assign_roles
from helpers.logger import get_logger

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
                "<:testSquad:1308586340996349952> **Welcome, to TEST Squadron - Best Squardon!** <:BESTSquad:1308586367303028756>\n\n"
                "We're thrilled to have you as a MAIN member of **TEST Squadron!**\n\n"
                "Join our voice chats, explore events, and engage in our text channels to make the most of your experience!\n\n"
                "Fly safe! <:o7:1306961462215970836>"
            )
        elif assigned_role_type == 'affiliate':
            description = (
                "<:testSquad:1308586340996349952> **Welcome, to TEST Squadron - Best Squardon!** <:BESTSquad:1308586367303028756>\n\n"
                "Your support helps us grow and excel. We encourage you to set **TEST** as your MAIN Org to show your loyalty.\n\n"
                "**Instructions:**\n"
                ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
                "1️⃣ Click **Set as Main** next to **TEST Squadron**.\n\n"
                "Join our voice chats, explore events, and engage in our text channels to get involved!\n\n"
                "<:o7:1306961462215970836>"
            )
        elif assigned_role_type == 'non_member':
            description = (
                "<:testSquad:1308586340996349952> **Welcome, to TEST Squadron - Best Squardon!** <:BESTSquad:1308586367303028756>\n\n"
                "It looks like you're not yet a member of our org. <:what:1306961532080623676>\n\n"
                "Join us for thrilling adventures and be part of the best and  biggest community!\n\n"
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


def can_modify_nickname(member: discord.Member) -> bool:
    """
    Checks if the bot can modify the member's nickname based on role hierarchy.

    Args:
        member (discord.Member): The member to check.

    Returns:
        bool: True if the bot can modify, False otherwise.
    """
    guild = member.guild
    bot_member = guild.me
    can_modify = bot_member.top_role > member.top_role
    logger.debug(f"Can modify nickname: {can_modify} (Bot Top Role: {bot_member.top_role}, Member Top Role: {member.top_role})")
    return can_modify
