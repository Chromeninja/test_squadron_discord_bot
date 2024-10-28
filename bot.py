import discord
from discord.ext import commands
from discord.ui import Button, View, Modal
import os
from dotenv import load_dotenv
import RSIVerify  
import GenDailyToken as GT   
import RSIBioVerify                                     

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Set up bot intents (needs to have member-related intents enabled in Discord Developer Portal)
intents = discord.Intents.default()
intents.members = True

# Initialize bot with command prefix and intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Channel ID where the bot sends verification message (replace with actual channel ID)
VERIFICATION_CHANNEL_ID = 1294734078356099147  # Replace with the channel ID

#Update Roles
NoneMember_ROLE_ID = 1296654331222954025
Main_ROLE_ID = 1296654035998474451
Affiliate_ROLE_ID = 1295070914345570417

class HandleModal(Modal):
    def __init__(self):
        dtoken = GT.generate_daily_token()
        super().__init__(title=f"First, change Star Citizen bio to {dtoken}")
        # Create a TextInput for the modal
        self.handle = discord.ui.TextInput(label="Verify", placeholder="Enter your Star Citizen handle here")
        # Add the TextInput to the modal
        self.add_item(self.handle)

    async def on_submit(self, interaction: discord.Interaction):
        # Handle submission logic
        star_citizen_handle = self.handle.value
        verify_value = is_valid_rsi_handle(star_citizen_handle)
        tokenverify_value = is_valid_rsi_bio(star_citizen_handle)

        member = interaction.user

        if verify_value == 1 and tokenverify_value == 1:
            role = interaction.guild.get_role(Main_ROLE_ID)
            await member.edit(nick=star_citizen_handle)
            await interaction.response.send_message(f"Your nickname has been updated to {star_citizen_handle}!", ephemeral=True)
        elif verify_value == 2 and tokenverify_value == 1:
            role = interaction.guild.get_role(Affiliate_ROLE_ID)
            await member.edit(nick=star_citizen_handle)
            await interaction.response.send_message(f"Your nickname has been updated to {star_citizen_handle}!", ephemeral=True)
        else:
            role = interaction.guild.get_role(NoneMember_ROLE_ID)
            await member.edit(nick="KickMe")
            await interaction.response.send_message(f"Your nickname has been updated to Kickme!", ephemeral=True)        


        await member.add_roles(role)
        await interaction.followup.send(f"You have been assigned the {role.name} role!", ephemeral=True)




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

    url = f"https://robertsspaceindustries.com/citizens/{user_handle}/organizations"
    org_data = RSIVerify.scrape_rsi_organizations(url)
    verify_data = RSIVerify.search_organization(org_data,"TEST Squadron - Best Squardon!")
    return verify_data

def is_valid_rsi_bio(user_handle):

    url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    biotoken = RSIBioVerify.extract_bio(url)
    tokenverify = RSIBioVerify.verifytoken(biotoken)
    return tokenverify

# Replace with your bot token
bot.run(TOKEN)
