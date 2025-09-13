# Helpers/modals.py

import contextlib
import re

import discord
from discord.ui import Modal, TextInput

from config.config_loader import ConfigLoader
from helpers.discord_api import (
    edit_channel,
    followup_send_message,
)
from helpers.embeds import (
    create_cooldown_embed,
    create_error_embed,
    create_success_embed,
)
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from helpers.rate_limiter import (
    check_rate_limit,
    get_remaining_attempts,
    log_attempt,
    reset_attempts,
)
from helpers.role_helper import assign_roles
from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import flush_tasks
from helpers.token_manager import clear_token, token_store, validate_token
from helpers.voice_utils import get_user_channel, update_channel_settings
from utils.logging import get_logger
from verification.rsi_verification import is_valid_rsi_bio, is_valid_rsi_handle

logger = get_logger(__name__)

# Load configuration
config = ConfigLoader.load_config()
ORG_NAME = config["organization"]["name"]

# Regular expression to validate RSI handle format
RSI_HANDLE_REGEX = re.compile(r"^[A-Za-z0-9\[\]][A-Za-z0-9_\-\s\[\]]{0,59}$")


class HandleModal(Modal, title="Verification"):
    """
    Modal to collect the user's RSI handle for verification.
    """

    rsi_handle = TextInput(
        label="RSI Handle",
        placeholder="Enter your Star Citizen handle here",
        max_length=60,
    )

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """
        Handles the submission of the verification modal.

        Args:
            interaction (discord.Interaction): The interaction triggered by the modal submission.
        """
        # 1) Immediately defer the interaction to avoid multiple .response calls:
        await interaction.response.defer(ephemeral=True)
        logger.debug(
            "Deferred response for HandleModal verification.",
            extra={"user_id": interaction.user.id},
        )

        member = interaction.user
        rsi_handle_input = self.rsi_handle.value.strip()

        # Validate RSI handle format
        if not RSI_HANDLE_REGEX.match(rsi_handle_input):
            embed = create_error_embed(
                "Invalid RSI Handle. Use letters, numbers, _, -, and spaces. Max 60 chars (e.g., 'TEST-B3st_123')."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning("Invalid RSI handle format.", extra={"user_id": member.id})
            return

            # Proceed with verification to get verify_value and cased_handle
        verify_value, cased_handle, community_moniker = await is_valid_rsi_handle(
            rsi_handle_input, self.bot.http_client
        )
        if verify_value is None or cased_handle is None:  # moniker optional
            embed = create_error_embed(
                "Failed to verify RSI handle. Please check and try again."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning(
                "Verification failed: invalid RSI handle.", extra={"user_id": member.id}
            )
            return

            # Validate token
        user_token_info = token_store.get(member.id)
        if not user_token_info:
            embed = create_error_embed(
                "No active token found. Please click 'Get Token' to receive a new token."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning(
                "Verification attempted without a token.", extra={"user_id": member.id}
            )
            return

        valid, message = validate_token(member.id, user_token_info["token"])
        if not valid:
            embed = create_error_embed(message)
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning(
                "Invalid/expired token provided.", extra={"user_id": member.id}
            )
            return

            # Perform RSI verification with sanitized handle
        verify_value_check, _cased_handle_2, community_moniker_2 = (
            await is_valid_rsi_handle(cased_handle, self.bot.http_client)
        )
        if verify_value_check is None:
            embed = create_error_embed(
                "Failed to verify RSI handle. Please check your handle again."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning("RSI verification failed.", extra={"user_id": member.id})
            return

        # Determine which cased handle to use (prefer the freshly-extracted one)
        cased_handle_used = _cased_handle_2 or cased_handle
        # Prefer the second call's community moniker if present
        community_moniker = community_moniker_2 or community_moniker

        token_verify = await is_valid_rsi_bio(
            cased_handle_used, user_token_info["token"], self.bot.http_client
        )
        if token_verify is None:
            embed = create_error_embed(
                "Failed to verify token in RSI bio. Ensure your token is in your bio."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning(
                "Verification failed: token not found in bio.",
                extra={"user_id": member.id},
            )
            return

            # 6) Log attempt & check if user exceeded max attempts
        await log_attempt(member.id, "verification")

        # Check if verification failed
        if verify_value_check is None or not token_verify:
            remaining_attempts = await get_remaining_attempts(member.id, "verification")
            if remaining_attempts <= 0:
                # User has exceeded max attempts
                _, wait_until = await check_rate_limit(member.id, "verification")

                # Get retry time in seconds for better user feedback
                import time

                retry_after_seconds = (
                    int(wait_until - time.time()) if wait_until > time.time() else 0
                )

                # Create and send the cooldown embed with enhanced feedback
                embed = create_cooldown_embed(wait_until)
                await followup_send_message(
                    interaction, "", embed=embed, ephemeral=True
                )
                logger.info(
                    "User exceeded verification attempts. Cooldown enforced.",
                    extra={
                        "user_id": member.id,
                        "remaining_attempts": 0,
                        "retry_after": retry_after_seconds,
                    },
                )
            else:
                error_msg = []
                if verify_value_check is None:
                    error_msg.append("- Could not verify RSI organization membership.")
                elif verify_value_check == 0:
                    # Check if this might be due to hidden affiliations
                    error_msg.append(
                        f"- You are not a member of {ORG_NAME} or its affiliates."
                    )
                    error_msg.append(
                        f"- If your {ORG_NAME} affiliation is hidden on RSI, please make it visible temporarily so we can verify affiliate status."
                    )
                if not token_verify:
                    error_msg.append("- Token not found or mismatch in bio.")
                error_msg.append(
                    f"You have {remaining_attempts} attempts left before cooldown."
                )
                embed = create_error_embed("\n".join(error_msg))
                await followup_send_message(
                    interaction, "", embed=embed, ephemeral=True
                )
                logger.info(
                    "User failed verification.",
                    extra={
                        "user_id": member.id,
                        "remaining_attempts": remaining_attempts,
                        "verify_value": verify_value_check,
                        "token_verify": token_verify,
                    },
                )
            return

        # Leadership log: snapshot before
        import time as _t

        _start = _t.time()
        before_snap = await snapshot_member_state(self.bot, member)

        # Verification successful
        old_status, assigned_role_type = await assign_roles(
            member,
            verify_value_check,
            cased_handle_used,
            self.bot,
            community_moniker=community_moniker,
        )
        # Allow enqueued role/nick tasks to process so snapshot reflects changes
        with contextlib.suppress(Exception):
            await flush_tasks()
        after_snap = await snapshot_member_state(self.bot, member)
        diff = diff_snapshots(before_snap, after_snap)
        cs = ChangeSet(
            user_id=member.id,
            event=EventType.VERIFICATION,
            initiator_kind="User",
            initiator_name=None,
            notes=None,
        )
        for k, v in diff.items():
            setattr(cs, k, v)
        cs.started_at = before_snap and cs.started_at  # preserve default
        # duration tracking removed
        try:
            await post_if_changed(self.bot, cs)
        except Exception:
            logger.debug("Leadership log post failed (verification modal)")
        clear_token(member.id)
        await reset_attempts(member.id)

        # Send customized success message based on role
        if assigned_role_type == "main":
            description = (
                f"<:testSquad:1332572066804928633> **Welcome, to {ORG_NAME} - "
                "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
                f"We're thrilled to have you as a MAIN member of **{ORG_NAME}!**\n\n"
                "Join our voice chats, explore events, and engage in our text channels to "
                "make the most of your experience!\n\n"
                "Fly safe! <:o7:1332572027877593148>"
            )
        elif assigned_role_type == "affiliate":
            description = (
                f"<:testSquad:1332572066804928633> **Welcome, to {ORG_NAME} - "
                "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
                "Your support helps us grow and excel. We encourage you to set **TEST** as "
                "your MAIN Org to show your loyalty.\n\n"
                "**Instructions:**\n"
                ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
                f"1️⃣ Click **Set as Main** next to **{ORG_NAME}**.\n\n"
                "Join our voice chats, explore events, and engage in our text channels to get "
                "involved!\n\n"
                "<:o7:1332572027877593148>"
            )
        elif assigned_role_type == "non_member":
            description = (
                f"<:testSquad:1332572066804928633> **Welcome, to {ORG_NAME} - "
                "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
                "It looks like you're not yet a member of our org. <:what:1332572046638452736>\n\n"
                "Join us for thrilling adventures and be part of the best and biggest community!\n\n"
                f"🔗 [Join {ORG_NAME}](https://robertsspaceindustries.com/orgs/TEST)\n"
                "*Click **Enlist Now!**. Test membership requests are usually approved within "
                "24-72 hours. You will need to reverify to update your roles once approved.*\n\n"
                "Join our voice chats, explore events, and engage in our text channels to get "
                "involved! <:o7:1332572027877593148>"
            )
        else:
            description = (
                "Welcome to the server! You can verify again after 3 hours if needed."
            )

        if "We set your Discord nickname" not in description:
            description += "\n\nWe set your Discord nickname to your RSI handle."
        embed = create_success_embed(description)

        # 9) Send follow-up success
        try:
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info(
                "User successfully verified.",
                extra={
                    "user_id": member.id,
                    "rsi_handle": cased_handle_used,
                    "assigned_role": assigned_role_type,
                },
            )
        except Exception:
            logger.exception(
                "Failed to send verification success message",
                extra={"user_id": member.id},
            )


class ResetSettingsConfirmationModal(Modal):
    """
    Modal to confirm resetting channel settings.
    """

    def __init__(self, bot, guild_id=None, jtc_channel_id=None) -> None:
        super().__init__(title="Reset Channel Settings", timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.jtc_channel_id = jtc_channel_id
        self.confirm = TextInput(
            label="Type 'RESET' to confirm",
            placeholder="RESET",
            required=True,
            min_length=5,
            max_length=5,
        )
        self.add_item(self.confirm)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Defer the response to acknowledge the interaction
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild_id = self.guild_id or interaction.guild.id
        confirmation_text = self.confirm.value.strip().upper()
        if confirmation_text != "RESET":
            await followup_send_message(
                interaction,
                "Confirmation text does not match. Channel settings were not reset.",
                ephemeral=True,
            )
            logger.info(f"{member.display_name} failed to confirm channel reset.")
            return

            # Try resetting channel settings using the modern voice service
        try:
            # Access the Voice cog to reset channel settings
            voice_cog = self.bot.get_cog("voice")
            if not voice_cog:
                await followup_send_message(
                    interaction, "Voice cog is not loaded.", ephemeral=True
                )
                logger.error("Voice cog not found.")
                return

            # Use the modern purge method for this specific user and JTC channel
            guild_id = interaction.guild_id
            user_id = member.id

            # Delete user's managed channel if it exists
            channel_result = await voice_cog.voice_service.delete_user_owned_channel(
                guild_id, user_id
            )

            # Purge voice data for this user with cache cleanup
            deleted_counts = (
                await voice_cog.voice_service.purge_voice_data_with_cache_clear(
                    guild_id, user_id
                )
            )

            total_deleted = sum(deleted_counts.values())

            success_msg = "✅ Your channel settings have been reset to default."
            if channel_result.get("channel_deleted"):
                success_msg += "\n🗑️ Your voice channel was also deleted."
            if total_deleted > 0:
                success_msg += f"\n📊 Cleared {total_deleted} database records."

            await followup_send_message(
                interaction,
                success_msg,
                ephemeral=True,
            )
            logger.info(
                f"{member.display_name} reset their channel settings - deleted {total_deleted} records"
            )
        except Exception:
            logger.exception(
                f"Error resetting channel settings for {member.display_name}"
            )
            await followup_send_message(
                interaction,
                "An error occurred while resetting your channel settings. Please try again later.",
                ephemeral=True,
            )


class NameModal(Modal):
    """
    Modal to change the voice channel name.
    """

    def __init__(self, bot, guild_id=None, jtc_channel_id=None) -> None:
        super().__init__(title="Change Channel Name", timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.jtc_channel_id = jtc_channel_id
        self.channel_name = TextInput(
            label="New Channel Name",
            placeholder="Enter a new name for your channel",
            min_length=2,
            max_length=32,
        )
        self.add_item(self.channel_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Defer immediately
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        new_name = self.channel_name.value.strip()
        guild_id = self.guild_id or interaction.guild.id

        if not (2 <= len(new_name) <= 32):
            await followup_send_message(
                interaction,
                "Channel name must be between 2 and 32 characters.",
                ephemeral=True,
            )
            return

        channel = await get_user_channel(
            self.bot, member, guild_id, self.jtc_channel_id
        )
        if not channel:
            await followup_send_message(
                interaction, "You don't own a channel.", ephemeral=True
            )
            return

        try:
            await edit_channel(channel, name=new_name)
            await update_channel_settings(
                member.id, guild_id, self.jtc_channel_id, channel_name=new_name
            )

            await followup_send_message(
                interaction,
                f"Channel name has been changed to '{new_name}'.",
                ephemeral=True,
            )
            logger.info(f"{member.display_name} changed channel name to '{new_name}'.")
        except discord.Forbidden:
            logger.warning(
                f"Insufficient permissions to change channel name for {member.display_name}."
            )
            await followup_send_message(
                interaction,
                "I don't have permission to change the channel name.",
                ephemeral=True,
            )
        except Exception:
            logger.exception(f"Failed to change channel name for {member.display_name}")
            await followup_send_message(
                interaction,
                "An unexpected error occurred. Please try again later.",
                ephemeral=True,
            )


class LimitModal(Modal):
    """
    Modal to set the user limit for the voice channel.
    """

    def __init__(self, bot, guild_id=None, jtc_channel_id=None) -> None:
        super().__init__(title="Set User Limit", timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.jtc_channel_id = jtc_channel_id
        self.user_limit = TextInput(
            label="User Limit",
            placeholder="Enter a number between 2 and 99",
            required=True,
            max_length=2,
        )
        self.add_item(self.user_limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Defer immediately
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild_id = self.guild_id or interaction.guild.id

        try:
            limit = int(self.user_limit.value.strip())
            if not (2 <= limit <= 99):
                raise ValueError
        except ValueError:
            embed = create_error_embed("User limit must be a number between 2 and 99.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

            # Update user limit
        channel = await get_user_channel(
            self.bot, member, guild_id, self.jtc_channel_id
        )
        if not channel:
            await followup_send_message(
                interaction, "You don't own a channel.", ephemeral=True
            )
            return

        try:
            await edit_channel(channel, user_limit=limit)

            # Update settings using the helper function
            await update_channel_settings(
                member.id, guild_id, self.jtc_channel_id, user_limit=limit
            )

            embed = create_success_embed(f"User limit has been set to {limit}.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info(
                f"{member.display_name} set their channel user limit to {limit}."
            )
        except discord.Forbidden:
            logger.warning(
                f"Insufficient permissions to set user limit for {member.display_name}."
            )
            embed = create_error_embed("I don't have permission to set the user limit.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Failed to set user limit")
            embed = create_error_embed("Failed to set user limit. Please try again.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
