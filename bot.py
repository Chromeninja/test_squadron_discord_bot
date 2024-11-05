# bot.py

import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
import logging
from dotenv import load_dotenv
import asyncio
import time

# Import our new modules
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
VERIFICATION_CHANNEL_ID = 1301647270889914429  # Replace with your verification channel ID
BOT_VERIFIED_ROLE_ID = 987654321098765432      # Replace with your BotVerified role ID
MAIN_ROLE_ID = 1179505821760114689             # Replace with your Main role ID
AFFILIATE_ROLE_ID = 1179618003604750447        # Replace with your Affiliate role ID
NON_MEMBER_ROLE_ID = 1301648113483907132       # Replace with your NonMember role ID

# Configurable parameters
MAX_ATTEMPTS = 3
COOLDOWN_TIME = 30 * 60  # 30 minutes in seconds

# In-memory storage for tracking user attempts, cooldowns, and daily verifications
user_attempts = {}
user_cooldowns = {}
user_daily_cooldowns = {}

class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)
        # Add buttons
        self.get_token_button = Button(label="Get Token", style=discord.ButtonStyle.success)
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        self.verify_button = Button(label="Verify", style=discord.ButtonStyle.primary)
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

    async def get_token_button_callback(self, interaction: discord.Interaction):
        member = interaction.user

        # Check for daily cooldown
        current_time = time.time()
        daily_cooldown = user_daily_cooldowns.get(member.id, 0)
        if current_time < daily_cooldown:
            remaining = int(daily_cooldown - current_time)
            hours, remainder = divmod(remaining, 3600)
            minutes, _ = divmod(remainder, 60)
            await interaction.response.send_message(
                f"You can verify again in {hours} hours and {minutes} minutes.", ephemeral=True)
            return

        # Check for cooldown from failed attempts
        if member.id in user_cooldowns and current_time < user_cooldowns[member.id]:
            remaining = int(user_cooldowns[member.id] - current_time)
            minutes, seconds = divmod(remaining, 60)
            await interaction.response.send_message(
                f"You are on cooldown. Please try again in {minutes} minutes and {seconds} seconds.", ephemeral=True)
            return

        # Generate token and send via ephemeral message
        token = generate_token(member.id)

        # Send the token directly in an ephemeral message with updated instructions
        await interaction.response.send_message(
            f"Hello! :wave:\n\n"
            f"Use this token for verification: `{token}`\n\n"
            f"**Instructions:**\n"
            f":one: Go to your [RSI account profile](<https://robertsspaceindustries.com/account/profile>).\n"
            f":two: Add the token to your **Short Bio** field.\n"
            f":three: Scroll down and click **Apply All Changes**.\n"
            f":four: Return here and click the 'Verify' button below.\n\n"
            f":information_source: *Note: The token expires in 15 minutes.*",
            ephemeral=True
        )

    async def verify_button_callback(self, interaction: discord.Interaction):
        member = interaction.user

        # Check for cooldown
        if member.id in user_cooldowns and time.time() < user_cooldowns[member.id]:
            remaining = int(user_cooldowns[member.id] - time.time())
            minutes, seconds = divmod(remaining, 60)
            await interaction.response.send_message(
                f"You are on cooldown. Please try again in {minutes} minutes and {seconds} seconds.", ephemeral=True)
            return

        # Show the modal to get RSI handle
        modal = HandleModal()
        await interaction.response.send_modal(modal)

class HandleModal(Modal, title="Verification"):
    rsi_handle = TextInput(label="RSI Handle", placeholder="Enter your Star Citizen handle here")

    async def on_submit(self, interaction: discord.Interaction):
    member = interaction.user
    rsi_handle_value = self.rsi_handle.value.strip()

    # Check if the user has an active token
    user_token_info = token_store.get(member.id)
    if not user_token_info:
        await interaction.response.send_message(
            "No active token found. Please click 'Get Token' to receive a new token.", ephemeral=True)
        return

    valid, message = validate_token(member.id, user_token_info['token'])
    if not valid:
        await interaction.response.send_message(message, ephemeral=True)
        return

    # Defer the response as verification may take some time
    await interaction.response.defer(ephemeral=True)

    token = user_token_info['token']

    # Perform RSI verification
    verify_value = await is_valid_rsi_handle(rsi_handle_value)
    token_verify = await is_valid_rsi_bio(rsi_handle_value, token)

    # Handle attempts
    attempts = user_attempts.get(member.id, 0) + 1
    user_attempts[member.id] = attempts

    if not verify_value or not token_verify:
        # Verification failed
        if attempts >= MAX_ATTEMPTS:
            user_cooldowns[member.id] = time.time() + COOLDOWN_TIME
            user_attempts[member.id] = 0  # Reset attempts after cooldown is set
            await interaction.followup.send(
                f"You have reached the maximum number of attempts. Please try again after {COOLDOWN_TIME // 60} minutes.",
                ephemeral=True)
            return
        else:
            error_message = "Verification failed due to the following reasons:\n"
            if not verify_value:
                error_message += "- Could not verify RSI organization membership.\n"
            if not token_verify:
                error_message += "- Token not found or does not match in RSI bio.\n"
            error_message += f"You have {MAX_ATTEMPTS - attempts} attempts remaining before cooldown."
            await interaction.followup.send(error_message, ephemeral=True)
            return

    # Verification successful
    assigned_role_type = await assign_roles(member, verify_value, rsi_handle_value)
    clear_token(member.id)
    user_attempts.pop(member.id, None)  # Reset attempts on success

    # Set daily cooldown
    user_daily_cooldowns[member.id] = time.time() + 86400  # 24 hours in seconds

    # Send customized success message based on role
    if assigned_role_type == 'main':
        success_message = (
            "🎉 **Verification Successful!** 🎉\n\n"
            "Thank you for being a main member of **TEST Squadron - Best Squardon!** "
            "We're thrilled to have you with us. Be sure to check out the events section at the top for lastest events. o7"
        )
    elif assigned_role_type == 'affiliate':
        success_message = (
            "🎉 **Verification Successful!** 🎉\n\n"
            "Thanks for being an affiliate of **TEST Squadron - Best Squardon!** "
            "Consider setting **TEST** as your Main Org to share in the glory of TEST.\n\n"
            "**Instructions:**\n"
            ":point_right: [Change Your Main Org](<https://robertsspaceindustries.com/account/organization>)\n"
            "1️⃣ Click on **Set as Main** next to **TEST**."
        )
    elif assigned_role_type == 'non_member':
        success_message = (
            "🎉 **Verification Successful!** 🎉\n\n"
            "Welcome! It looks like you're not a member of **TEST Squadron - Best Squardon!** "
            "Join us to be part of the adventure!\n\n"
            "🔗 [Join TEST Squadron](<https://robertsspaceindustries.com/orgs/TEST>)\n"
            "*Click **Enlist Now!**. Test membership requests are usually approved within 24-72 hours.*"
        )
    else:
        success_message = (
            "🎉 **Verification Successful!** 🎉\n\n"
            "Welcome to the server! You can verify again after 24 hours if needed."
        )

    await interaction.followup.send(
        success_message,
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

        # Send the static verification message
        view = VerificationView()
        await channel.send("Welcome! Please verify yourself by clicking the buttons below.", view=view)
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
