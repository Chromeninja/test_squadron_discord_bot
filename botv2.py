import discord
from discord.ext import commands
from discord.ui import Button, View, Modal
import os
from dotenv import load_dotenv
import RSIVerify  
import GenDailyToken as GT   
import RSIBioVerify                                     
import aiohttp  
import logging  

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

VERIFICATION_CHANNEL_ID = 1301647270889914429  

NoneMember_ROLE_ID = 1301648113483907132
Main_ROLE_ID = 1179505821760114689
Affiliate_ROLE_ID = 1179618003604750447

class HandleModal(Modal):
    def __init__(self):
        dtoken = GT.generate_daily_token()
        super().__init__(title=f"First, change Star Citizen bio to {dtoken}")
        self.handle = discord.ui.TextInput(label="Verify", placeholder="Enter your Star Citizen handle here")
        self.add_item(self.handle)

    async def on_submit(self, interaction: discord.Interaction):
        star_citizen_handle = self.handle.value
        
        # Await the asynchronous functions
        verify_value = is_valid_rsi_handle(star_citizen_handle)
        tokenverify_value = is_valid_rsi_bio(star_citizen_handle)

        
        member = interaction.user

        if verify_value == 1 and tokenverify_value == 1:
            role_id = Main_ROLE_ID
            message = f"Your nickname has been updated to {star_citizen_handle}!"
        elif verify_value == 2 and tokenverify_value == 1:
            role_id = Affiliate_ROLE_ID
            message = f"Your nickname has been updated to {star_citizen_handle}!"
        else:
            role_id = NoneMember_ROLE_ID
            star_citizen_handle = "KickMe"
            message = "Your nickname has been updated to KickMe!"

        try:
            role = interaction.guild.get_role(role_id)
            await member.edit(nick=star_citizen_handle)
            await member.add_roles(role)
            await interaction.response.send_message(message, ephemeral=True)
            await interaction.followup.send("Success!", ephemeral=True)
        except Exception as e:
            logging.error(f"Error updating member {member.id}: {e}")
            await interaction.response.send_message("An error occurred during verification. Please try again later.", ephemeral=True)


class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)

        # Add the Success button first to ensure it appears to the left
        self.success_button = Button(label="Get Token", style=discord.ButtonStyle.success)
        self.success_button.callback = self.success_button_callback
        self.add_item(self.success_button)

        # Add the Verify button
        self.verify_button = Button(label="Verify", style=discord.ButtonStyle.primary)
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

    async def verify_button_callback(self, interaction: discord.Interaction):
        modal = HandleModal()
        await interaction.response.send_modal(modal)

    async def success_button_callback(self, interaction: discord.Interaction):
        # Send the "Please stand up!" message when Success button is clicked
        dtoken = GT.generate_daily_token()
        await interaction.response.send_message(f"Please enter the following token into your Star Citizen Bio {dtoken}", ephemeral=True)


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
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

bot.run(TOKEN)