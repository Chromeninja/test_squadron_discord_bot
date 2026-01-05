import json

import discord
from discord.ext import commands

from helpers.discord_api import followup_send_message
from helpers.embeds import (
    build_welcome_description,
    create_cooldown_embed,
    create_error_embed,
    create_success_embed,
    create_verification_embed,
)
from helpers.leadership_log import InitiatorKind, InitiatorSource
from helpers.recheck_service import perform_recheck
from helpers.views import VerificationView
from services.db.repository import BaseRepository
from utils.logging import get_logger
from utils.tasks import spawn

logger = get_logger(__name__)


async def _load_verification_message_ids_from_db() -> dict[int, int]:
    """Load verification message IDs for all guilds from database."""
    message_ids: dict[int, int] = {}
    try:
        rows = await BaseRepository.fetch_all(
            "SELECT guild_id, value FROM guild_settings WHERE key = 'channels.verification_message_id'"
        )
        for row in rows:
            try:
                guild_id = int(row[0])
                message_id = json.loads(row[1])
                message_ids[guild_id] = int(message_id)
            except (ValueError, json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Invalid verification message ID for guild {row[0]}: {e}")
        logger.info(f"Loaded {len(message_ids)} verification message IDs from database")
    except Exception as e:
        logger.exception("Failed to load verification message IDs from database", exc_info=e)
    return message_ids


async def _save_verification_message_to_db(guild_id: int, message_id: int) -> None:
    """Save a verification message ID for a guild to database."""
    try:
        await BaseRepository.execute(
            "INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?) ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
            (guild_id, "channels.verification_message_id", json.dumps(message_id)),
        )
        logger.debug(f"Saved verification message ID {message_id} for guild {guild_id}")
    except Exception as e:
        logger.exception(f"Failed to save verification message ID for guild {guild_id}", exc_info=e)


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

    async def send_verification_message(
        self, guilds: list[discord.Guild] | None = None
    ) -> None:
        """
        Send verification messages to provided guilds (all guilds by default).

        If a message already exists for a guild, it will not send a new one.
        """
        target_guilds = guilds or list(self.bot.guilds)

        logger.info(
            "Starting to send verification messages to %s guild(s)...",
            len(target_guilds),
        )

        if not target_guilds:
            logger.error("Bot has no guilds, cannot send verification messages")
            return

        for idx, g in enumerate(target_guilds, 1):
            logger.info(f"  Guild {idx}: {g.name} (ID: {g.id})")

        guild_config = self.bot.services.guild_config  # type: ignore[attr-defined]
        message_ids = await _load_verification_message_ids_from_db()
        updated_message_ids = message_ids.copy()

        guilds_processed = 0
        guilds_sent = 0
        guilds_skipped = 0
        guilds_failed = 0

        for guild in self.bot.guilds:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Processing guild: {guild.name} (ID: {guild.id})")
            logger.info(f"{'=' * 60}")
            guilds_processed += 1

            try:
                # Clear cache to ensure fresh data for multi-guild support
                logger.debug(
                    f"Clearing cache for guild {guild.id} to ensure fresh config data"
                )
                try:
                    await self.bot.services.config.clear_guild_cache(guild.id)  # type: ignore[attr-defined]
                except Exception as cache_err:
                    logger.warning(
                        f"Failed to clear cache for guild {guild.id}: {cache_err}"
                    )

                # Get verification channel from config service
                logger.info(
                    f"Looking up verification_channel_id for guild {guild.id}..."
                )
                channel = await guild_config.get_channel(
                    guild.id, "verification_channel_id", guild
                )

                logger.info(f"Channel lookup result: {channel}")
                if channel:
                    logger.info(
                        f"  ✓ Found channel: #{channel.name} (ID: {channel.id})"
                    )
                    logger.info(f"  ✓ Channel type: {type(channel).__name__}")
                    logger.info(
                        f"  ✓ Bot permissions in channel: send_messages={channel.permissions_for(guild.me).send_messages}, embed_links={channel.permissions_for(guild.me).embed_links}"
                    )
                else:
                    logger.warning(
                        "  ✗ Channel is None - no verification channel configured"
                    )

                if channel is None:
                    logger.warning(
                        f"✗ No verification channel configured for guild {guild.name} ({guild.id})"
                    )
                    logger.warning(
                        "  Skipping this guild - please configure verification channel in settings"
                    )
                    guilds_skipped += 1
                    continue

                # Check if message already exists for this guild
                existing_message_id = message_ids.get(guild.id)
                logger.info(
                    f"Existing message ID for this guild: {existing_message_id}"
                )

                if existing_message_id:
                    logger.info(
                        f"Checking if message {existing_message_id} still exists..."
                    )
                    try:
                        # Try to fetch the message
                        existing_msg = await channel.fetch_message(existing_message_id)
                        logger.info(
                            f"✓ Verification message already exists for {guild.name} (Message ID: {existing_message_id})"
                        )
                        logger.info(f"  Message created at: {existing_msg.created_at}")
                        logger.info("  Skipping - message already present")
                        guilds_skipped += 1
                        continue  # Message already exists, no need to send a new one
                    except discord.NotFound:
                        logger.info(
                            f"✗ Message {existing_message_id} not found - will send a new one"
                        )
                    except discord.Forbidden:
                        logger.warning(
                            f"✗ No permission to fetch message {existing_message_id} - will try to send new one"
                        )
                    except Exception as e:
                        logger.warning(
                            f"✗ Error fetching message {existing_message_id}: {e} - will send new one"
                        )
                else:
                    logger.info(
                        f"No existing message ID found for guild {guild.id} - will send new message"
                    )

                # Fetch organization logo URL for the embed thumbnail
                logo_url = None
                try:
                    logo_url = await guild_config.get_setting(
                        guild.id, "organization.logo_url", default=None
                    )
                    if logo_url:
                        logger.info(f"Using organization logo: {logo_url}")
                except Exception as e:
                    logger.warning(f"Failed to fetch org logo URL: {e}")

                # Create the verification embed with logo
                logger.info("Creating verification embed...")
                embed = create_verification_embed(thumbnail_url=logo_url)

                # Initialize the verification view with buttons
                logger.info("Creating verification view with buttons...")
                view = VerificationView(self.bot)

                # Send the embed with the interactive view to the channel
                try:
                    logger.info(
                        f"Attempting to send verification embed to #{channel.name}..."
                    )
                    sent_message = await channel.send(embed=embed, view=view)
                    logger.info(f"✓ SUCCESS: Sent verification message to {guild.name}")
                    logger.info(f"  Message ID: {sent_message.id}")
                    logger.info(f"  Channel: #{channel.name} ({channel.id})")
                    logger.info(f"  Message URL: {sent_message.jump_url}")

                    # Save the message ID for this guild
                    updated_message_ids[guild.id] = sent_message.id
                    guilds_sent += 1

                except discord.Forbidden as e:
                    logger.exception(
                        f"✗ FAILED: Bot lacks permission to send messages in {guild.name}"
                    )
                    logger.exception(f"  Channel: #{channel.name} ({channel.id})")
                    logger.exception(
                        "  Required permissions: Send Messages, Embed Links"
                    )
                    logger.exception(f"  Error: {e}")
                    guilds_failed += 1
                except discord.HTTPException as e:
                    logger.exception(
                        f"✗ FAILED: HTTP error sending verification message to {guild.name}"
                    )
                    logger.exception(f"  Error: {e}")
                    guilds_failed += 1

            except Exception as e:
                logger.exception(
                    f"✗ EXCEPTION processing guild {guild.name} ({guild.id}): {e}"
                )
                logger.exception("Full traceback:", exc_info=e)
                guilds_failed += 1
                continue

        # Save all message IDs atomically
        logger.info(f"\n{'=' * 60}")
        logger.info("VERIFICATION MESSAGE SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"Guilds processed: {guilds_processed}")
        logger.info(f"Messages sent: {guilds_sent}")
        logger.info(f"Guilds skipped (already have message): {guilds_skipped}")
        logger.info(f"Failed: {guilds_failed}")
        logger.info(f"Total message IDs to save: {len(updated_message_ids)}")

        if updated_message_ids != message_ids:
            logger.info(
                f"Saving {len(updated_message_ids)} message IDs to database..."
            )
            for guild_id, msg_id in updated_message_ids.items():
                await _save_verification_message_to_db(guild_id, msg_id)
            logger.info("✓ Successfully saved verification message IDs")
            for guild_id, msg_id in updated_message_ids.items():
                logger.info(f"  Guild {guild_id}: Message {msg_id}")
        else:
            logger.info("No changes to message IDs - skipping save")

        logger.info(f"{'=' * 60}\n")

    async def recheck_button(self, interaction: discord.Interaction) -> None:
        """Handle a user-initiated recheck via the verification view button."""
        await interaction.response.defer(ephemeral=True)
        member = interaction.user

        # Fetch existing verification record
        rsi_handle = await BaseRepository.fetch_value(
            "SELECT rsi_handle FROM verification WHERE user_id = ?", (member.id,)
        )
        if not rsi_handle:
            embed = create_error_embed("You are not verified yet. Please click Verify first.")
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Ensure member is a Member, not just User
        if not isinstance(member, discord.Member):
            embed = create_error_embed(
                "This command can only be used by server members."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Perform unified recheck
        result = await perform_recheck(
            member=member,
            rsi_handle=rsi_handle,
            bot=self.bot,
            initiator_kind=InitiatorKind.USER,
            initiator_source=InitiatorSource.BUTTON,
            enforce_rate_limit=True,
            log_leadership=True,
            log_audit=False,  # User-initiated, no admin audit needed
        )

        # Handle rate limiting
        if result["rate_limited"]:
            embed = create_cooldown_embed(result["wait_until"])
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Handle remediation (404)
        if result["remediated"]:
            verification_channel_id = getattr(self.bot, "VERIFICATION_CHANNEL_ID", 0)
            embed = create_error_embed(
                f"Your RSI Handle appears to have changed. Please re-verify in <#{verification_channel_id}>."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Handle other errors
        if not result["success"]:
            embed = create_error_embed(
                result["error"] or "Re-check failed. Please try again later."
            )
            await followup_send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Success!
        new_status = result["status"]
        description = build_welcome_description(new_status)
        embed = create_success_embed(description)
        await followup_send_message(interaction, "", embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
