# cogs/verification.py

import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import time
import logging
import asyncio

from helpers.embeds import (
    create_error_embed,
    create_success_embed
)
from helpers.token_manager import (
    generate_token,
    validate_token,
    clear_token,
    token_store
)
from verification.rsi_verification import (
    is_valid_rsi_handle,
    is_valid_rsi_bio
)
from helpers.role_helper import get_roles
from config.config_loader import ConfigLoader  # Import the ConfigLoader

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()

MAX_ATTEMPTS = config['rate_limits']['max_attempts']
RATE_LIMIT_WINDOW = config['rate_limits']['window_seconds']

# In-memory storage for tracking user verification attempts
user_verification_attempts = {}

class VerificationCog(commands.Cog):
    """
    Cog to handle user verification within the Discord server.
    """
    def __init__(self, bot):
        """
        Initializes the VerificationCog with the bot instance.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.verification_channel_id = bot.VERIFICATION_CHANNEL_ID
        # Create a background task for sending the verification message
        self.bot.loop.create_task(self.send_verification_message())

    async def send_verification_message(self):
        """
        Sends the initial verification message to the verification channel.
        """
        logging.info("Starting to send verification message...")
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.verification_channel_id)
        if channel is None:
            logging.error(f"Could not find the channel with ID {self.verification_channel_id}.")
            return
        else:
            logging.info(f"Found verification channel: {channel.name} (ID: {self.verification_channel_id})")

        # Clear all messages in the verification channel
        logging.info("Clearing messages in the verification channel...")
        await self.clear_verification_channel(channel)
        logging.info("Cleared messages in the verification channel.")

        # Create the embed with yellow color
        embed = discord.Embed(
            title="📡 Account Verification",
            description=(
                "Welcome! To get started, please **click the 'Get Token' button below**.\n\n"
                "After obtaining your token, verify your RSI / Star Citizen account by using the provided buttons.\n\n"
                "If you don't have an account, feel free to [enlist here](https://robertsspaceindustries.com/enlist?referral=STAR-MXL7-VM6G)."
            ),
            color=0xFFBB00  # Yellow color in hexadecimal
        )
        embed.set_thumbnail(url="https://robertsspaceindustries.com/static/images/logo.png")  # Example thumbnail

        # Initialize the verification view with buttons
        view = VerificationView(self.bot)

        # Send the embed with the interactive view to the channel
        try:
            logging.info("Attempting to send the verification embed...")
            await channel.send(embed=embed, view=view)
            logging.info("Sent verification message in channel.")
        except Exception as e:
            logging.exception(f"Failed to send verification message: {e}")

    async def clear_verification_channel(self, channel):
        """
        Clears all messages from the specified verification channel.

        Args:
            channel (discord.TextChannel): The channel to clear messages from.
        """
        logging.info("Attempting to clear verification channel messages...")
        try:
            # Fetch all messages in the channel
            messages = []
            async for message in channel.history(limit=None):
                messages.append(message)

            # Bulk delete messages if possible (only messages younger than 14 days)
            if messages:
                try:
                    await channel.delete_messages(messages)
                    logging.info(f"Deleted {len(messages)} messages in the verification channel.")
                except discord.HTTPException as e:
                    logging.warning(f"Bulk delete failed: {e}. Attempting individual deletions.")

                    # Fallback to deleting messages individually
                    for message in messages:
                        try:
                            await message.delete()
                            await asyncio.sleep(1)  # Add delay to prevent rate limits
                        except Exception as ex:
                            logging.exception(f"Failed to delete message {message.id}: {ex}")
            else:
                logging.info("No messages to delete in the verification channel.")
        except discord.Forbidden:
            logging.error("Bot lacks permission to delete messages in the verification channel.")
        except discord.HTTPException as e:
            logging.exception(f"Failed to delete messages: {e}")

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
        logging.info(f"'Get Token' button clicked by user {interaction.user} (ID: {interaction.user.id})")
        member = interaction.user
        current_time = time.time()

        # Initialize the user's attempt list if not present
        attempts = user_verification_attempts.get(member.id, [])

        # Remove attempts that are outside the RATE_LIMIT_WINDOW
        attempts = [timestamp for timestamp in attempts if current_time - timestamp < RATE_LIMIT_WINDOW]
        user_verification_attempts[member.id] = attempts  # Update after cleanup

        if len(attempts) >= MAX_ATTEMPTS:
            # Calculate time until the earliest attempt expires
            earliest_attempt = attempts[0]
            wait_until = int(earliest_attempt + RATE_LIMIT_WINDOW)  # UNIX timestamp when cooldown ends

            # Create and send cooldown embed
            description = (
                f"You have reached the maximum number of verification attempts.\n"
                f"Please try again <t:{wait_until}:R>."
            )
            embed = discord.Embed(
                title="⏰ Cooldown Active",
                description=description,
                color=0xFFA500  # Orange color
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logging.info(f"User {member} reached max verification attempts.")
            return

        # Proceed to generate and send token
        token = generate_token(member.id)
        expires_at = token_store[member.id]['expires_at']
        expires_unix = int(expires_at)
        user_verification_attempts.setdefault(member.id, []).append(current_time)  # Log this attempt

        # Create and send token embed
        embed = discord.Embed(
            title="📡 Account Verification",
            description=(
                "Use the **4-digit PIN** below for verification.\n\n"
                "**Instructions:**\n"
                ":one: Login to your [RSI account profile](https://robertsspaceindustries.com/account/profile).\n"
                ":two: Add the PIN to your **Short Bio** field.\n"
                ":three: Scroll down and click **Apply All Changes**.\n"
                ":four: Return here and click the 'Verify' button below.\n\n"
                f":information_source: *Note: The PIN expires <t:{expires_unix}:R>.*"
            ),
            color=0x00FF00  # Green color
        )
        embed.set_thumbnail(url="https://robertsspaceindustries.com/static/images/logo.png")  # Example thumbnail

        # Add the token in a separate field with a colored code block to make it stand out
        embed.add_field(
            name="🔑 Your Verification PIN",
            value=f"```diff\n+ {token}\n```\n*On mobile, hold to copy*",
            inline=False
        )

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logging.info(f"Sent verification PIN to user {member} (ID: {member.id}).")
        except Exception as e:
            logging.exception(f"Failed to send verification PIN to user {member}: {e}")

    async def verify_button_callback(self, interaction: discord.Interaction):
        """
        Callback for the "Verify" button. Initiates the verification modal.

        Args:
            interaction (discord.Interaction): The interaction triggered by the button click.
        """
        logging.info(f"'Verify' button clicked by user {interaction.user} (ID: {interaction.user.id})")
        member = interaction.user
        current_time = time.time()

        # Initialize the user's attempt list if not present
        attempts = user_verification_attempts.get(member.id, [])

        # Remove attempts that are outside the RATE_LIMIT_WINDOW
        attempts = [timestamp for timestamp in attempts if current_time - timestamp < RATE_LIMIT_WINDOW]
        user_verification_attempts[member.id] = attempts  # Update after cleanup

        if len(attempts) >= MAX_ATTEMPTS:
            # Calculate time until the earliest attempt expires
            earliest_attempt = attempts[0]
            wait_until = int(earliest_attempt + RATE_LIMIT_WINDOW)  # UNIX timestamp when cooldown ends

            # Create and send cooldown embed
            description = (
                f"You have reached the maximum number of verification attempts.\n"
                f"Please try again <t:{wait_until}:R>."
            )
            embed = discord.Embed(
                title="⏰ Cooldown Active",
                description=description,
                color=0xFFA500  # Orange color
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logging.info(f"User {member} reached max verification attempts.")
            return

        # Show the modal to get RSI handle
        modal = HandleModal(self.bot)
        await interaction.response.send_modal(modal)
        logging.info(f"Displayed verification modal to user {member}.")

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

        # Handle attempts
        attempts = user_verification_attempts.get(member.id, [])
        # Remove outdated attempts
        attempts = [timestamp for timestamp in attempts if time.time() - timestamp < RATE_LIMIT_WINDOW]
        attempts.append(time.time())
        user_verification_attempts[member.id] = attempts

        if not verify_value or not token_verify:
            # Verification failed
            if len(attempts) >= MAX_ATTEMPTS:
                # User has exceeded max attempts
                earliest_attempt = attempts[0]
                wait_until = int(earliest_attempt + RATE_LIMIT_WINDOW)  # UNIX timestamp

                # Create the cooldown description with dynamic countdown
                description = (
                    f"You have reached the maximum number of verification attempts.\n"
                    f"Please try again <t:{wait_until}:R>."
                )

                # Create and send the enhanced cooldown embed
                embed = discord.Embed(
                    title="⏰ Cooldown Active",
                    description=description,
                    color=0xFFA500  # Orange color
                )

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
                remaining_attempts = MAX_ATTEMPTS - len(attempts)
                if remaining_attempts > 0:
                    error_details.append(f"You have {remaining_attempts} attempt(s) remaining before cooldown.")
                error_message = "\n".join(error_details)
                embed = create_error_embed(error_message)
                await interaction.followup.send(embed=embed, ephemeral=True)
                logging.info(f"User {member} failed verification. Remaining attempts: {remaining_attempts}.")
                return

        # Verification successful
        assigned_role_type = await assign_roles(member, verify_value, rsi_handle_value, self.bot)
        clear_token(member.id)
        user_verification_attempts.pop(member.id, None)  # Reset attempts on success

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

async def assign_roles(member, verify_value, rsi_handle_value, bot):
    """
    Assigns roles to the member based on their verification status.

    Args:
        member (discord.Member): The member to assign roles to.
        verify_value (int): Verification status (1: main, 2: affiliate, 0: non-member).
        rsi_handle_value (str): The RSI handle of the user.
        bot (commands.Bot): The bot instance.

    Returns:
        str: The type of role assigned ('main', 'affiliate', 'non_member', or 'unknown').
    """
    guild = member.guild
    role_ids = [
        bot.BOT_VERIFIED_ROLE_ID,
        bot.MAIN_ROLE_ID,
        bot.AFFILIATE_ROLE_ID,
        bot.NON_MEMBER_ROLE_ID
    ]
    roles = await get_roles(guild, role_ids)
    bot_verified_role, main_role, affiliate_role, non_member_role = roles

    # Remove conflicting roles
    roles_to_remove = [role for role in [main_role, affiliate_role, non_member_role] if role in member.roles]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Updating roles after verification")
            logging.info(f"Removed roles: {[role.name for role in roles_to_remove]} from user {member}.")
        except Exception as e:
            logging.exception(f"Failed to remove roles from user {member}: {e}")

    # Assign roles based on verification outcome
    roles_to_add = []
    assigned_role_type = None  # To keep track of the role type assigned

    if bot_verified_role and bot_verified_role not in member.roles:
        roles_to_add.append(bot_verified_role)

    if verify_value == 1 and main_role:
        roles_to_add.append(main_role)
        assigned_role_type = 'main'
    elif verify_value == 2 and affiliate_role:
        roles_to_add.append(affiliate_role)
        assigned_role_type = 'affiliate'
    elif non_member_role:
        roles_to_add.append(non_member_role)
        assigned_role_type = 'non_member'

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Roles assigned after verification")
            logging.info(f"Assigned roles: {[role.name for role in roles_to_add]} to user {member}.")
        except Exception as e:
            logging.exception(f"Failed to assign roles to user {member}: {e}")
            assigned_role_type = 'unknown'
    else:
        logging.error("No valid roles to add.")
        assigned_role_type = 'unknown'

    # Check role hierarchy before attempting to change nickname
    bot_top_role = guild.me.top_role
    member_top_role = member.top_role

    if bot_top_role > member_top_role:
        # Bot's role is higher; attempt to change nickname
        try:
            await member.edit(nick=rsi_handle_value[:32])
            logging.info(f"Nickname changed to {rsi_handle_value[:32]} for user {member}.")
        except discord.Forbidden:
            logging.warning("Bot lacks permission to change this member's nickname due to role hierarchy.")
        except Exception as e:
            logging.exception(f"Unexpected error when changing nickname for user {member}: {e}")
    else:
        logging.warning("Cannot change nickname due to role hierarchy.")

    return assigned_role_type

async def setup(bot):
    """
    Asynchronous setup function to add the VerificationCog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(VerificationCog(bot))
