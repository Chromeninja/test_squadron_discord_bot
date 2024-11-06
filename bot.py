# bot.py

import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
import logging
from dotenv import load_dotenv
import asyncio
import time

# Import helper functions for embeds
from helpers import (
    create_cooldown_embed,
    create_error_embed,
    create_success_embed
)

# Import our existing modules
from token_manager import generate_token, validate_token, clear_token, token_store
from verification import is_valid_rsi_handle, is_valid_rsi_bio

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Needed for receiving messages

bot = commands.Bot(command_prefix="!", intents=intents)

# Constants (replace with your actual IDs)
VERIFICATION_CHANNEL_ID = int(os.getenv('VERIFICATION_CHANNEL_ID'))
BOT_VERIFIED_ROLE_ID = int(os.getenv('BOT_VERIFIED_ROLE_ID'))
MAIN_ROLE_ID = int(os.getenv('MAIN_ROLE_ID'))
AFFILIATE_ROLE_ID = int(os.getenv('AFFILIATE_ROLE_ID'))
NON_MEMBER_ROLE_ID = int(os.getenv('NON_MEMBER_ROLE_ID'))

# Configurable parameters
MAX_ATTEMPTS = 3
RATE_LIMIT_WINDOW = 3 * 60 * 60  # 3 hours in seconds

# In-memory storage for tracking user verification attempts
user_verification_attempts = {}

class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)
        # Add "Get Token" button
        self.get_token_button = Button(label="Get Token", style=discord.ButtonStyle.success)
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        # Add "Verify" button
        self.verify_button = Button(label="Verify", style=discord.ButtonStyle.primary)
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

    async def get_token_button_callback(self, interaction: discord.Interaction):
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
            wait_time = RATE_LIMIT_WINDOW - (current_time - earliest_attempt)
            hours, remainder = divmod(int(wait_time), 3600)
            minutes, _ = divmod(remainder, 60)

            # Create and send cooldown embed
            description = (
                f"You have reached the maximum number of verification attempts.\n"
                f"Please try again in {hours} hours and {minutes} minutes."
            )
            embed = create_cooldown_embed(description, unit="hours" if hours > 0 else "minutes")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Proceed to generate and send token
        token = generate_token(member.id)
        user_verification_attempts.setdefault(member.id, []).append(current_time)  # Log this attempt

        # Create and send token embed
        embed = discord.Embed(
            title="📡 Account Verification",
            description=(
                f"Use this **4-digit PIN** for verification: `**{token}**`\n\n"
                f"**Instructions:**\n"
                f":one: Go to your [RSI account profile](https://robertsspaceindustries.com/account/profile).\n"
                f":two: Add the PIN to your **Short Bio** field.\n"
                f":three: Scroll down and click **Apply All Changes**.\n"
                f":four: Return here and click the 'Verify' button below.\n\n"
                f":information_source: *Note: The PIN expires in 15 minutes.*"
            ),
            color=0x00FF00  # Green color
        )
        embed.set_thumbnail(url="https://robertsspaceindustries.com/static/images/logo.png")  # Example thumbnail

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def verify_button_callback(self, interaction: discord.Interaction):
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
            wait_time = RATE_LIMIT_WINDOW - (current_time - earliest_attempt)
            hours, remainder = divmod(int(wait_time), 3600)
            minutes, _ = divmod(remainder, 60)

            # Create and send cooldown embed
            description = (
                f"You have reached the maximum number of verification attempts.\n"
                f"Please try again in {hours} hours and {minutes} minutes."
            )
            embed = create_cooldown_embed(description, unit="hours" if hours > 0 else "minutes")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Show the modal to get RSI handle
        modal = HandleModal()
        await interaction.response.send_modal(modal)

class HandleModal(Modal, title="Verification"):
    rsi_handle = TextInput(label="RSI Handle", placeholder="Enter your Star Citizen handle here", max_length=32)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        rsi_handle_input = self.rsi_handle.value.strip()

        # Normalize the RSI handle to lowercase for case-insensitive handling
        rsi_handle_value = rsi_handle_input.lower()

        # Check if the user has an active token
        user_token_info = token_store.get(member.id)
        if not user_token_info:
            embed = create_error_embed("No active token found. Please click 'Get Token' to receive a new token.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        valid, message = validate_token(member.id, user_token_info['token'])
        if not valid:
            embed = create_error_embed(message)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer the response as verification may take some time
        await interaction.response.defer(ephemeral=True)

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
                wait_time = RATE_LIMIT_WINDOW - (time.time() - attempts[0])
                hours, remainder = divmod(int(wait_time), 3600)
                minutes, _ = divmod(remainder, 60)
                description = (
                    f"You have reached the maximum number of attempts.\n"
                    f"Please try again after {hours} hours and {minutes} minutes."
                )
                embed = create_cooldown_embed(description, unit="hours" if hours > 0 else "minutes")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            else:
                # Prepare error details
                error_details = []
                if not verify_value:
                    error_details.append("- Could not verify RSI organization membership.")
                if not token_verify:
                    error_details.append("- Token not found or does not match in RSI bio.")
                error_details.append(f"You have {MAX_ATTEMPTS - len(attempts)} attempts remaining before cooldown.")
                error_message = "\n".join(error_details)
                embed = create_error_embed(error_message)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        # Verification successful
        assigned_role_type = await assign_roles(member, verify_value, rsi_handle_value)
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

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

async def assign_roles(member, verify_value, rsi_handle_value):
    guild = member.guild
    bot_verified_role = guild.get_role(BOT_VERIFIED_ROLE_ID)
    main_role = guild.get_role(MAIN_ROLE_ID)
    affiliate_role = guild.get_role(AFFILIATE_ROLE_ID)
    non_member_role = guild.get_role(NON_MEMBER_ROLE_ID)

    # Log the retrieved roles
    logging.info(f"Bot Verified Role: {bot_verified_role}")
    logging.info(f"Main Role: {main_role}")
    logging.info(f"Affiliate Role: {affiliate_role}")
    logging.info(f"Non-Member Role: {non_member_role}")

    # Remove conflicting roles
    roles_to_remove = [role for role in [main_role, affiliate_role, non_member_role] if role]
    await member.remove_roles(*roles_to_remove, reason="Updating roles after verification")

    # Assign roles based on verification outcome
    roles_to_add = []
    assigned_role_type = None  # To keep track of the role type assigned

    if bot_verified_role:
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
        await member.add_roles(*roles_to_add, reason="Roles assigned after verification")
        logging.info(f"Assigned roles: {[role.name for role in roles_to_add]}")
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
            logging.info(f"Nickname changed to {rsi_handle_value[:32]}")
        except discord.Forbidden:
            logging.warning("Bot lacks permission to change this member's nickname due to role hierarchy.")
        except Exception as e:
            logging.exception(f"Unexpected error when changing nickname: {e}")
    else:
        logging.warning("Cannot change nickname due to role hierarchy.")

    return assigned_role_type

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logging.info("Connected guilds:")
    for guild in bot.guilds:
        logging.info(f"- {guild.name} (ID: {guild.id})")

    try:
        # Get the verification channel
        channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        if channel is None:
            logging.error(f"Could not find the channel with ID {VERIFICATION_CHANNEL_ID}")
            return
        else:
            logging.info(f"Found channel: {channel.name} (ID: {channel.id})")

        # Clear all messages in the verification channel
        logging.info("Clearing messages in the verification channel...")
        await clear_verification_channel(channel)
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
        view = VerificationView()

        # Send the embed with the interactive view to the channel
        await channel.send(embed=embed, view=view)
        logging.info("Sent verification message in channel.")

    except Exception as e:
        logging.exception(f"An error occurred in on_ready: {e}")

async def clear_verification_channel(channel):
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
    except discord.Forbidden:
        logging.error("Bot lacks permission to delete messages in the verification channel.")
    except discord.HTTPException as e:
        logging.exception(f"Failed to delete messages: {e}")

bot.run(TOKEN)
