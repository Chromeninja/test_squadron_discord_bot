import discord
from discord.ext import commands
from discord.ui import Button, View, Modal
import os
from dotenv import load_dotenv
import RSIVerify                                            

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Set up bot intents (needs to have member-related intents enabled in Discord Developer Portal)
intents = discord.Intents.default()
intents.members = True

# Initialize bot with command prefix and intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Channel ID where the bot sends verification message (replace with actual channel ID)
VERIFICATION_CHANNEL_ID = 1294734078356099147  # Replace with the channel ID

class HandleModal(Modal):
    def __init__(self):
        super().__init__(title="Enter Your Star Citizen Handle")
        # Create a TextInput for the modal
        self.handle = discord.ui.TextInput(label="Star Citizen Handle", placeholder="Enter your handle here")
        # Add the TextInput to the modal
        self.add_item(self.handle)

    async def on_submit(self, interaction: discord.Interaction):
        # Handle submission logic
        star_citizen_handle = self.handle.value

        if is_valid_rsi_handle(star_citizen_handle):

            member = interaction.user

            # Update the member's nickname with the Star Citizen Handle
            try:
                await member.edit(nick=star_citizen_handle)
                await interaction.response.send_message(f"Your nickname has been updated to {star_citizen_handle}!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I don't have permission to change your nickname.", ephemeral=True)


class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.primary)
    async def verify_button_callback(self,interaction: discord.Interaction, button: Button):
        # Display the modal when the button is clicked
        modal = HandleModal()
        # Correctly call the interaction's response method to send the modal
        await interaction.response.send_modal(modal)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_member_join(member):
    # Send a verification message to a specific channel when a user joins
    channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
    if channel:
        view = VerificationView()
        await channel.send(f"Welcome {member.mention}! Please verify yourself by clicking the button below.", view=view)


def is_valid_rsi_handle(user_handle):

     print(f"Code is good to here for {user_handle}!")
     return True

    # """
    # Check if the RSI handle is valid by querying the RSI website or API.
    # """
    # user = RSIVerify.User(user_handle=user_handle).execute()
    # print(user.get("profile", {}).get("handle", "not available"))
    # if not user:
    #     return False
    # return user.get("profile", {}).get("handle", "not available")



# Replace with your bot token
bot.run(TOKEN)
