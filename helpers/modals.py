import discord
from discord.ui import Modal, TextInput

from helpers.discord_api import (
    edit_channel,
    followup_send_message,
)
from helpers.embeds import (
    create_cooldown_embed,
    create_error_embed,
    create_success_embed,
)
from helpers.leadership_log import (
    EventType,
    InitiatorKind,
    InitiatorSource,
)
from helpers.rate_limiter import (
    check_rate_limit,
    get_remaining_attempts,
    log_attempt,
    reset_attempts,
)
from helpers.task_queue import flush_tasks
from helpers.token_manager import clear_token, token_store, validate_token
from helpers.verification_logging import log_guild_sync
from helpers.voice_utils import get_user_channel, update_channel_settings
from services.guild_sync import apply_state_to_guild, sync_user_to_all_guilds
from services.verification_scheduler import compute_next_retry, schedule_user_recheck
from services.verification_state import compute_global_state, store_global_state
from utils.logging import get_logger
from verification.rsi_verification import RSI_HANDLE_REGEX, is_valid_rsi_bio

logger = get_logger(__name__)


async def get_org_name(bot, guild_id: int) -> str:
    """
    Get organization name from config service.

    Args:
        bot: Bot instance with config service
        guild_id: Guild ID for config lookup

    Returns:
        Organization name (defaults to 'TEST' if not configured)
    """
    org_name = "TEST"  # Default fallback
    if hasattr(bot, "services") and hasattr(bot.services, "guild_config"):
        try:
            org_name_config = await bot.services.guild_config.get_setting(
                guild_id, "organization.name", default="TEST"
            )
            org_name = org_name_config.strip() if org_name_config else "TEST"
        except Exception as e:
            logger.warning(
                f"Failed to get org name from config, using default: {e}",
                extra={"guild_id": guild_id},
            )
    return org_name


async def get_org_sid(bot, guild_id: int) -> str | None:
    """
    Get organization SID from config service.

    Args:
        bot: Bot instance with config service
        guild_id: Guild ID for config lookup

    Returns:
        Organization SID (uppercase) or None if not configured
    """
    if hasattr(bot, "services") and hasattr(bot.services, "guild_config"):
        try:
            org_sid_config = await bot.services.guild_config.get_setting(
                guild_id, "organization.sid", default=None
            )
            if org_sid_config:
                return org_sid_config.strip().upper()
        except Exception as e:
            logger.warning(
                f"Failed to get org SID from config: {e}", extra={"guild_id": guild_id}
            )
    return None


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
        # Defer the interaction immediately to avoid multiple response calls
        await interaction.response.defer(ephemeral=True)
        logger.debug(
            "Deferred response for HandleModal verification.",
            extra={"user_id": interaction.user.id},
        )

        # Ensure we have a guild and member context
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            embed = create_error_embed("This command can only be used in a server.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        member = interaction.user

        # Check rate limit FIRST before processing anything
        rate_limited, wait_until = await check_rate_limit(member.id, "verification")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info(
                "User tried to verify while rate limited.", extra={"user_id": member.id}
            )
            return

        rsi_handle_input = self.rsi_handle.value.strip()

        # DEBUG: Log guild context
        logger.info(
            f"HandleModal.on_submit: interaction.guild={interaction.guild.name} ({interaction.guild.id}), "
            f"member.guild={member.guild.name} ({member.guild.id}), "
            f"member.id={member.id}"
        )

        # Validate RSI handle format
        if not RSI_HANDLE_REGEX.match(rsi_handle_input):
            embed = create_error_embed(
                "Invalid RSI Handle. Use letters, numbers, _, -, and spaces. Max 60 chars (e.g., 'TEST-B3st_123')."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning("Invalid RSI handle format.", extra={"user_id": member.id})
            return

        # Validate token first (before expensive RSI calls)
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

        # Get organization config from guild
        org_name = await get_org_name(self.bot, interaction.guild.id)
        org_sid = await get_org_sid(self.bot, interaction.guild.id)

        # Use unified pipeline: compute_global_state for RSI verification
        try:
            global_state = await compute_global_state(
                member.id,
                rsi_handle_input,
                self.bot.http_client,
                config=getattr(self.bot, "config", None),
                org_name=org_name.lower(),
                force_refresh=True,  # Force fresh check for initial verification
            )
        except Exception as e:
            embed = create_error_embed(
                "Failed to verify RSI handle. Please check and try again."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning(
                "Verification failed: RSI fetch error: %s", e, extra={"user_id": member.id}
            )
            return

        # Check if RSI verification succeeded
        if global_state.error or not global_state.rsi_handle:
            embed = create_error_embed(
                "Failed to verify RSI handle. Please check your handle again."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            logger.warning("RSI verification failed.", extra={"user_id": member.id})
            return

        cased_handle_used = global_state.rsi_handle

        # Verify token in RSI bio
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

        # Log verification attempt
        await log_attempt(member.id, "verification")

        # Check if bio token verification failed
        if not token_verify:
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
                error_msg = ["- Token not found or mismatch in bio."]
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
                        "token_verify": token_verify,
                    },
                )
            return

        # Preflight: ensure RSI handle isn't already claimed before we apply roles
        try:
            from services.db.database import Database

            conflict = await Database.check_rsi_handle_conflict(
                global_state.rsi_handle, global_state.user_id
            )
            if conflict:
                raise ValueError("RSI handle is already verified by another Discord account.")
        except ValueError as e:
            error_msg = str(e)
            if "already verified by another Discord account" in error_msg:
                error_msg = (
                    "❌ **This RSI handle is already verified by another Discord user.**\n\n"
                    "Each RSI handle can only be linked to one Discord account.\n\n"
                    "If you believe this is an error, please contact a moderator."
                )
            embed = create_error_embed(error_msg)
            await followup_send_message(
                interaction, "", embed=embed, ephemeral=True
            )
            logger.warning(
                f"Verification failed: {e!s}",
                extra={"user_id": member.id, "rsi_handle": cased_handle_used},
            )
            return
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to validate verification state: %s", e)
            embed = create_error_embed("Failed to validate verification. Please try again.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Apply to current guild before persisting so leadership log can diff old vs new
        result = await apply_state_to_guild(global_state, member.guild, self.bot)
        await flush_tasks()

        # Persist global state after Discord updates to preserve correct before/after snapshots
        try:
            await store_global_state(global_state)
        except ValueError as e:
            error_msg = str(e)
            if "already verified by another Discord account" in error_msg:
                error_msg = (
                    "❌ **This RSI handle is already verified by another Discord user.**\n\n"
                    "Each RSI handle can only be linked to one Discord account.\n\n"
                    "If you believe this is an error, please contact a moderator."
                )
            embed = create_error_embed(error_msg)
            await followup_send_message(
                interaction, "", embed=embed, ephemeral=True
            )
            logger.warning(
                f"Verification failed during persistence: {e!s}",
                extra={"user_id": member.id, "rsi_handle": cased_handle_used},
            )
            return
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to persist verification state: %s", e)
            embed = create_error_embed("Failed to save verification. Please try again.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Log the change with proper initiator metadata
        if result:
            await log_guild_sync(
                result,
                EventType.VERIFICATION,
                self.bot,
                initiator={
                    "user_id": member.id,
                    "kind": InitiatorKind.USER,
                    "source": InitiatorSource.BUTTON,
                },
            )

        # Schedule auto-recheck using unified scheduler
        config = getattr(self.bot, "config", None)
        next_retry = compute_next_retry(global_state, config=config)
        await schedule_user_recheck(member.id, next_retry)

        # Sync to all other guilds where user is a member
        try:
            await sync_user_to_all_guilds(global_state, self.bot)
        except Exception as e:
            logger.warning(
                "Failed to sync user to other guilds: %s", e, extra={"user_id": member.id}
            )

        # Clean up token and reset rate limit
        clear_token(member.id)
        await reset_attempts(member.id)

        # Determine assigned role type for success message
        assigned_role_type = global_state.status

        # Send customized success message based on role
        if assigned_role_type == "main":
            description = (
                f"<:testSquad:1332572066804928633> **Welcome, to {org_name} - "
                "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
                f"We're thrilled to have you as a MAIN member of **{org_name}!**\n\n"
                "Join our voice chats, explore events, and engage in our text channels to "
                "make the most of your experience!\n\n"
                "Fly safe! <:o7:1332572027877593148>"
            )
        elif assigned_role_type == "affiliate":
            # Use org_sid for instructions
            org_sid_display = org_sid if org_sid else "TEST"
            description = (
                f"<:testSquad:1332572066804928633> **Welcome, to {org_name} - "
                "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
                f"Your support helps us grow and excel. We encourage you to set **{org_sid_display}** as "
                "your MAIN Org to show your loyalty.\n\n"
                "**Instructions:**\n"
                ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
                f"1️⃣ Click **Set as Main** next to **{org_name}**.\n\n"
                "Join our voice chats, explore events, and engage in our text channels to get "
                "involved!\n\n"
                "<:o7:1332572027877593148>"
            )
        elif assigned_role_type == "non_member":
            # Use org_sid for RSI URL
            org_sid_url = org_sid if org_sid else "TEST"
            description = (
                f"<:testSquad:1332572066804928633> **Welcome, to {org_name} - "
                "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
                "It looks like you're not yet a member of our org. <:what:1332572046638452736>\n\n"
                "Join us for thrilling adventures and be part of the best and biggest community!\n\n"
                f"🔗 [Join {org_name}](https://robertsspaceindustries.com/orgs/{org_sid_url})\n"
                f"*Click **Enlist Now!**. {org_name} membership requests are usually approved within "
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

        # Send follow-up success message
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

        if not interaction.guild:
            return

        member = interaction.user
        guild_id = self.guild_id or interaction.guild.id
        confirmation_text = self.confirm.value.strip().upper()
        if confirmation_text != "RESET":
            await followup_send_message(
                interaction,
                "Confirmation text does not match. Channel settings were not reset.",
                ephemeral=True,
            )
            logger.debug("User failed to confirm channel reset", extra={"user_id": member.id})
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
            logger.debug(
                "User reset channel settings",
                extra={"user_id": member.id, "records_deleted": total_deleted},
            )
        except Exception:
            logger.exception(
                "Error resetting channel settings", extra={"user_id": member.id}
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

        if not interaction.guild:
            return

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
            logger.debug("User changed channel name", extra={"user_id": member.id})
        except discord.Forbidden:
            logger.warning(
                "Insufficient permissions to change channel name",
                extra={"user_id": member.id},
            )
            await followup_send_message(
                interaction,
                "I don't have permission to change the channel name.",
                ephemeral=True,
            )
        except Exception:
            logger.exception("Failed to change channel name", extra={"user_id": member.id})
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

        if not interaction.guild:
            return

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
            logger.debug(
                "User set channel user limit",
                extra={"user_id": member.id, "limit": limit},
            )
        except discord.Forbidden:
            logger.warning(
                "Insufficient permissions to set user limit",
                extra={"user_id": member.id},
            )
            embed = create_error_embed("I don't have permission to set the user limit.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Failed to set user limit")
            embed = create_error_embed("Failed to set user limit. Please try again.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
