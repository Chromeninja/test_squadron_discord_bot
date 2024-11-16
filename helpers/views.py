# helpers/views.py

import discord
from discord.ui import Button, View

from helpers.embeds import create_token_embed, create_cooldown_embed
from helpers.token_manager import generate_token, token_store
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.modals import HandleModal
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

class VerificationView(View):
    """
    View containing interactive buttons for the verification process.
    """
    def __init__(self, bot):
        """
        Initializes the VerificationView with buttons.

        Args:
            bot (commands.Bot): The bot instance.
        """
        super().__init__(timeout=None)
        self.bot = bot
        # Add "Get Token" button
        self.get_token_button = Button(label="Get Token", style=discord.ButtonStyle.success)
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        # Add "Verify" button
        self.verify_button = Button(label="Verify", style=discord.ButtonStyle.primary)
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

    async def get_token_button_callback(self, interaction: discord.Interaction):
        """
        Callback for the "Get Token" button. Generates and sends a verification token to the user.

        Args:
            interaction (discord.Interaction): The interaction triggered by the button click.
        """
        logger.info("'Get Token' button clicked.", extra={'user_id': interaction.user.id})
        member = interaction.user

        # Check rate limit
        rate_limited, wait_until = check_rate_limit(member.id)
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        # Proceed to generate and send token
        token = generate_token(member.id)
        expires_at = token_store[member.id]['expires_at']
        expires_unix = int(expires_at)
        log_attempt(member.id)

        # Create and send token embed
        embed = create_token_embed(token, expires_unix)

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("Sent verification PIN to user.", extra={'user_id': member.id})
        except Exception as e:
            logger.exception(f"Failed to send verification PIN: {e}", extra={'user_id': member.id})

    async def verify_button_callback(self, interaction: discord.Interaction):
        """
        Callback for the "Verify" button. Initiates the verification modal.

        Args:
            interaction (discord.Interaction): The interaction triggered by the button click.
        """
        logger.info("'Verify' button clicked.", extra={'user_id': interaction.user.id})
        member = interaction.user

        # Check rate limit
        rate_limited, wait_until = check_rate_limit(member.id)
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        # Show the modal to get RSI handle
        modal = HandleModal(self.bot)
        await interaction.response.send_modal(modal)
        logger.info("Displayed verification modal to user.", extra={'user_id': member.id})
