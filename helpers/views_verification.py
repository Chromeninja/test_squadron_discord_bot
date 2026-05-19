"""
Verification Views

Interactive buttons for the Discord member verification flow:
  - VerificationView: Get Token, Verify (handle modal), and Re-Check buttons.
"""

from __future__ import annotations

import discord  # type: ignore[import-not-found]
from discord import Interaction  # type: ignore[import-not-found]
from discord.ui import Button, View  # type: ignore[import-not-found]

from helpers.embeds import create_cooldown_embed, create_token_embed
from helpers.modals import HandleModal
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.token_manager import generate_token, token_store
from utils.log_context import get_interaction_extra
from utils.logging import get_logger

logger = get_logger(__name__)


class VerificationView(View):
    """
    View containing interactive buttons for the verification process.

    Contains two buttons:
      - Get Token: Generates and sends a verification token.
      - Verify: Opens a modal to collect the user's RSI handle.
    """

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        self.get_token_button = Button(
            label="Get Token",
            style=discord.ButtonStyle.success,
            custom_id="verification_get_token_button",
        )
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        self.verify_button = Button(
            label="Verify",
            style=discord.ButtonStyle.primary,
            custom_id="verification_verify_button",
        )
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

        self.recheck_button = Button(
            label="Re-Check",
            style=discord.ButtonStyle.secondary,
            custom_id="verification_recheck_button",
        )
        self.recheck_button.callback = self.recheck_button_callback
        self.add_item(self.recheck_button)

    async def get_token_button_callback(self, interaction: Interaction) -> None:
        """
        Callback for the 'Get Token' button.

        Checks rate limits, generates a token, logs the attempt,
        and sends an embed with the token information.
        """
        # Defer immediately to prevent timeout during async operations
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        rate_limited, wait_until = await check_rate_limit(member.id, "verification")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await interaction.followup.send("", embed=embed, ephemeral=True)
            logger.info(
                "User reached max verification attempts",
                extra=get_interaction_extra(interaction),
            )
            return

        token = generate_token(member.id)
        expires_at = token_store[member.id]["expires_at"]
        expires_unix = int(expires_at)
        await log_attempt(member.id, "verification")

        embed = create_token_embed(token, expires_unix)
        try:
            await interaction.followup.send("", embed=embed, ephemeral=True)
            logger.info(
                "Sent verification token to user",
                extra=get_interaction_extra(interaction),
            )
        except Exception:
            logger.exception(
                "Failed to send verification token to user",
                extra=get_interaction_extra(interaction),
            )

    async def verify_button_callback(self, interaction: Interaction) -> None:
        """
        Callback for the 'Verify' button.

        Opens the HandleModal for user verification. Rate limiting is handled
        in the modal's on_submit method after validation.
        """
        modal = HandleModal(self.bot)
        try:
            await interaction.response.send_modal(modal)
        except discord.HTTPException as e:
            if e.code == 10062:  # Unknown interaction (expired)
                logger.warning(
                    "Interaction expired - user may have taken too long to click button",
                    extra={**get_interaction_extra(interaction), "error_code": e.code},
                )
                try:
                    await interaction.followup.send(
                        "⚠️ This verification button has expired. Please request a new verification message.",
                        ephemeral=True,
                    )
                except Exception:
                    logger.debug(
                        "Could not send expiration notice to user",
                        extra=get_interaction_extra(interaction),
                    )
            elif e.code == 40060:  # Interaction already acknowledged
                logger.warning(
                    "Interaction already acknowledged - user may have double-clicked button",
                    extra={**get_interaction_extra(interaction), "error_code": e.code},
                )
                try:
                    await interaction.followup.send(
                        "⚠️ Please enter your RSI handle in one attempt. If you clicked multiple times, please wait and try again.",
                        ephemeral=True,
                    )
                except Exception:
                    logger.debug(
                        "Could not send double-click notice to user",
                        extra=get_interaction_extra(interaction),
                    )
            else:
                raise

    async def recheck_button_callback(self, interaction: Interaction) -> None:
        verification_cog = self.bot.get_cog("VerificationCog")
        if verification_cog:
            await verification_cog.recheck_button(interaction)
        else:
            # Log a warning and inform the user
            logger.warning("VerificationCog is missing. Cannot process recheck_button.")
            await interaction.response.send_message(
                "Verification system is currently unavailable. Please try again later.",
                ephemeral=True,
            )
