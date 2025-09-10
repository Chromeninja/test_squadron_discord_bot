# Cogs/verification.py

import contextlib
import json
import os
from pathlib import Path

import discord
from discord.ext import commands

from helpers.database import Database
from helpers.discord_api import followup_send_message
from helpers.embeds import (
    build_welcome_description,
    create_cooldown_embed,
    create_error_embed,
    create_success_embed,
    create_verification_embed,
)
from helpers.http_helper import NotFoundError
from helpers.leadership_log import ChangeSet, EventType, post_if_changed
from helpers.logger import get_logger
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.role_helper import reverify_member
from helpers.snapshots import diff_snapshots, snapshot_member_state
from helpers.task_queue import flush_tasks
from helpers.username_404 import handle_username_404
from helpers.views import VerificationView
from utils.tasks import spawn

logger = get_logger(__name__)

# Data directory for storing bot state
data_dir = Path(os.environ.get("TESTBOT_STATE_DIR", "."))


def _load_verification_message_id() -> int | None:
    """
    Load the verification message ID from persistent storage.
    
    Returns:
        The message ID if found and valid, None otherwise.
    """
    message_id_file = data_dir / "verification_message_id.json"

    if not message_id_file.exists():
        return None

    try:
        data = json.loads(message_id_file.read_text(encoding="utf-8"))
        message_id = data.get("message_id")
        if isinstance(message_id, int):
            return message_id
        logger.warning(f"Invalid message_id type in {message_id_file}: {type(message_id)}")
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read verification message ID from {message_id_file}: {e}")
        return None


def _save_verification_message_id(message_id: int) -> None:
    """
    Save the verification message ID to persistent storage atomically.
    
    Args:
        message_id: The Discord message ID to save.
    """
    message_id_file = data_dir / "verification_message_id.json"

    try:
        # Ensure data directory exists
        data_dir.mkdir(parents=True, exist_ok=True)

        # Write to temporary file first for atomicity
        temp_file = message_id_file.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps({"message_id": message_id}, indent=2),
            encoding="utf-8"
        )

        # Atomic replace
        temp_file.replace(message_id_file)
        logger.info(f"Saved verification message ID {message_id} to {message_id_file}")

    except OSError as e:
        logger.error(f"Failed to save verification message ID to {message_id_file}: {e}")


class VerificationCog(commands.Cog):
    """
    Cog to handle user verification within the Discord server.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initializes the VerificationCog with the bot instance.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        # Schedule the verification message to be sent after the bot is ready
        spawn(self.wait_and_send_verification_message())

    async def wait_and_send_verification_message(self) -> None:
        """
        Waits until the bot is ready and sends the verification message.
        """
        await self.bot.wait_until_ready()
        await self.send_verification_message()

    async def send_verification_message(self) -> None:
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

        # Load the message ID from persistent storage
        message_id = _load_verification_message_id()

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
            except Exception as e:
                logger.warning(f"Error fetching verification message {message_id}: {e}")
                # Continue to create a new message

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

            # Save the message ID atomically
            _save_verification_message_id(sent_message.id)

        except discord.Forbidden:
            logger.exception(
                "Bot lacks permission to send messages in the verification channel."
            )
        except discord.HTTPException as e:
            logger.exception("Failed to send verification message")

    async def recheck_button(self, interaction: discord.Interaction) -> None:
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
                await followup_send_message(
                    interaction, "", embed=embed, ephemeral=True
                )
                return
            rsi_handle = row[0]

        # Rate limit check
        rate_limited, wait_until = await check_rate_limit(member.id, "recheck")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Snapshot BEFORE reverify to capture DB / handle / moniker changes
        import time as _t

        _start = _t.time()
        before_snap = await snapshot_member_state(self.bot, member)
        # Attempt re-verification (DB + role/nick tasks enqueued)
        try:
            result = await reverify_member(member, rsi_handle, self.bot)
        except NotFoundError:
            # Invoke unified remediation then inform user
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

        success, status_info, message = result
        if not success:
            embed = create_error_embed(
                message or "Re-check failed. Please try again later."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        if isinstance(status_info, tuple):
            _old_status, new_status = status_info
        else:
            new_status = status_info

        await log_attempt(member.id, "recheck")

        description = build_welcome_description(new_status)
        embed = create_success_embed(description)
        await followup_send_message(interaction, "", embed=embed, ephemeral=True)

        # Leadership log snapshot
        with contextlib.suppress(Exception):
            await flush_tasks()
        # Refetch member to get latest nickname / roles after queued tasks applied
        try:
            refreshed = await member.guild.fetch_member(member.id)
            if refreshed:
                member = refreshed
        except Exception:
            pass
        after_snap = await snapshot_member_state(self.bot, member)
        diff = diff_snapshots(before_snap, after_snap)
        try:
            if diff.get("username_before") == diff.get("username_after") and getattr(
                member, "_nickname_changed_flag", False
            ):
                pref = getattr(member, "_preferred_verification_nick", None)
                if pref and pref != diff.get("username_before"):
                    diff["username_after"] = pref
        except Exception:
            pass
        cs = ChangeSet(
            user_id=member.id,
            event=EventType.RECHECK,
            initiator_kind="User",
            initiator_name=None,
            notes=None,
        )
        for k, v in diff.items():
            setattr(cs, k, v)
        # duration tracking removed
        try:
            await post_if_changed(self.bot, cs)
        except Exception:
            logger.debug("Leadership log post failed (user recheck button)")


async def setup(bot: commands.Bot) -> None:
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
