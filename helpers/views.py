# helpers/views.py

import discord
from discord.ui import View, Select, Button, UserSelect, RoleSelect
from discord import SelectOption, Interaction
import json
from helpers.permissions_helper import apply_permissions_changes
from helpers.embeds import create_token_embed, create_error_embed, create_success_embed, create_cooldown_embed
from helpers.token_manager import generate_token, token_store
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.modals import HandleModal, NameModal, LimitModal
from helpers.logger import get_logger
from helpers.database import Database

# Initialize logger
logger = get_logger(__name__)

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
        member = interaction.user

        # Check rate limit
        rate_limited, wait_until = check_rate_limit(member.id)
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        # Proceed to generate and send token
        token = generate_token(member.id)
        expires_at = token_store[member.id]['expires_at']
        expires_unix = int(expires_at)
        log_attempt(member.id)

        # Create and send token embed
        embed = create_token_embed(token, expires_unix)

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to send verification PIN: {e}", extra={'user_id': member.id})

    async def verify_button_callback(self, interaction: discord.Interaction):
        """
        Callback for the "Verify" button. Initiates the verification modal.

        Args:
            interaction (discord.Interaction): The interaction triggered by the button click.
        """
        member = interaction.user

        # Check rate limit
        rate_limited, wait_until = check_rate_limit(member.id)
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        # Show the modal to get RSI handle
        modal = HandleModal(self.bot)
        await interaction.response.send_modal(modal)

class ChannelSettingsView(View):
    """
    View containing interactive select menus for channel settings and permissions.
    """
    def __init__(self, bot, member: discord.Member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member

        # Channel Settings Select Menu
        self.channel_settings_select = Select(
            placeholder="Channel Settings",
            min_values=1,
            max_values=1,
            options=[
                SelectOption(
                    label="Name",
                    value="name",
                    description="Change the name of the channel",
                    emoji="✏️"
                ),
                SelectOption(
                    label="Limit",
                    value="limit",
                    description="Set user limit for the channel",
                    emoji="🔢"
                ),
                SelectOption(
                    label="Game",
                    value="game",
                    description="Set channel name to your current game",
                    emoji="🎮"
                ),
            ]
        )
        self.channel_settings_select.callback = self.channel_settings_callback
        self.add_item(self.channel_settings_select)

        # Channel Permissions Select Menu
        self.channel_permissions_select = Select(
            placeholder="Channel Permissions",
            min_values=1,
            max_values=1,
            options=[
                SelectOption(
                    label="Lock",
                    value="lock",
                    description="Lock the channel",
                    emoji="🔒"
                ),
                SelectOption(
                    label="Unlock",
                    value="unlock",
                    description="Unlock the channel",
                    emoji="🔓"
                ),
                SelectOption(
                    label="Permit",
                    value="permit",
                    description="Permit users/roles to join",
                    emoji="✅"
                ),
                SelectOption(
                    label="Reject",
                    value="reject",
                    description="Reject users/roles from joining",
                    emoji="🚫"
                ),
                SelectOption(
                    label="Force PTT",
                    value="force_ptt",
                    description="Enable PTT for users/roles",
                    emoji="🎙️"
                ),
                SelectOption(
                    label="Disable PTT",
                    value="disable_ptt",
                    description="Disable PTT for users/roles",
                    emoji="🔊"
                ),
            ]
        )
        self.channel_permissions_select.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select)

    async def channel_settings_callback(self, interaction: discord.Interaction):
        selected = self.channel_settings_select.values[0]
        if selected == "name":
            modal = NameModal(self.bot, self.member)
            await interaction.response.send_modal(modal)
        elif selected == "limit":
            modal = LimitModal(self.bot, self.member)
            await interaction.response.send_modal(modal)
        elif selected == "game":
            channel = await self.bot.get_cog('voice')._get_user_channel(self.member)
            if not channel:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return

            game_name = self.bot.get_cog('voice')._get_user_game_name(self.member)
            if not game_name:
                await interaction.response.send_message("You are not currently playing a game.", ephemeral=True)
                return

            # Update channel name to game name
            try:
                await channel.edit(name=game_name[:32])  # Ensure name is within 32 characters
                async with Database.get_connection() as db:
                    await db.execute(
                        "UPDATE channel_settings SET channel_name = ? WHERE user_id = ?",
                        (game_name, self.member.id)
                    )
                    await db.commit()

                embed = discord.Embed(
                    description=f"Channel name has been set to your current game: **{game_name}**.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"{self.member.display_name} set their channel name to game: {game_name}.")
            except Exception as e:
                logger.exception(f"Failed to set channel name to game: {e}")
                embed = create_error_embed("Failed to set channel name to your current game. Please try again.")
                await interaction.response.send_message(embed=embed, ephemeral=True)

    async def channel_permissions_callback(self, interaction: discord.Interaction):
        selected = self.channel_permissions_select.values[0]
        if selected in ["permit", "reject", "force_ptt", "disable_ptt"]:
            action = selected
            view = TargetTypeSelectView(self.bot, self.member, action=action)
            await interaction.response.send_message("Choose the type of target you want to apply the action to:", view=view, ephemeral=True)
        elif selected in ["lock", "unlock"]:
            lock = True if selected == "lock" else False
            channel = await self.bot.get_cog('voice')._get_user_channel(self.member)
            if not channel:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return

            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.connect = not lock
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

            # Save the lock state in permissions
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT permissions FROM channel_settings WHERE user_id = ?",
                    (self.member.id,)
                )
                settings_row = await cursor.fetchone()
                permissions = {}
                if settings_row and settings_row[0]:
                    permissions = json.loads(settings_row[0])

                permissions['lock'] = lock

                await db.execute(
                    "INSERT OR REPLACE INTO channel_settings (user_id, permissions) VALUES (?, ?)",
                    (self.member.id, json.dumps(permissions))
                )
                await db.commit()

            status = "locked" if lock else "unlocked"
            await interaction.response.send_message(f"Your voice channel has been {status}.", ephemeral=True)
            logger.info(f"{self.member.display_name} {status} their voice channel.")
        else:
            await interaction.response.send_message("Unknown option selected.", ephemeral=True)

class TargetTypeSelectView(View):
    def __init__(self, bot, member, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.action = action
        self.enable = enable  # For PTT action

        self.target_type_select = Select(
            placeholder="Select Target Type",
            min_values=1,
            max_values=1,
            options=[
                SelectOption(label="User", value="user", description="Select users to apply the action"),
                SelectOption(label="Role", value="role", description="Select roles to apply the action"),
            ]
        )
        self.target_type_select.callback = self.target_type_callback
        self.add_item(self.target_type_select)

    async def target_type_callback(self, interaction: Interaction):
        selected_type = self.target_type_select.values[0]
        if selected_type == "user":
            view = SelectUserView(self.bot, self.member, self.action, enable=self.enable)
            await interaction.response.edit_message(content="Select users to apply the action:", view=view)
        elif selected_type == "role":
            view = SelectRoleView(self.bot, self.member, self.action, enable=self.enable)
            await interaction.response.edit_message(content="Select roles to apply the action:", view=view)
        else:
            await interaction.response.send_message("Unknown target type selected.", ephemeral=True)

class SelectUserView(View):
    """
    View to select multiple users.
    """
    def __init__(self, bot, member, action):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.action = action
        self.enable = enable

        self.user_select = UserSelect(
            placeholder="Select Users",
            min_values=1,
            max_values=25,
            custom_id="user_select"
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def user_select_callback(self, interaction: Interaction):
        selected_users = self.user_select.values
        selected_user_ids = [user.id for user in selected_users]
        channel = await self.bot.get_cog('voice')._get_user_channel(self.member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        targets = [{'type': 'user', 'id': user_id} for user_id in selected_user_ids]

        # Apply permissions
        try:
            await apply_permissions_changes(channel, {'action': self.action, 'targets': targets})
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Update database permissions
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT permissions FROM channel_settings WHERE user_id = ?",
                (self.member.id,)
            )
            settings_row = await cursor.fetchone()
            permissions = {}
            if settings_row and settings_row[0]:
                permissions = json.loads(settings_row[0])

            if 'permissions' not in permissions:
                permissions['permissions'] = []

            permissions['permissions'].append({'action': self.action, 'targets': targets})

            await db.execute(
                "INSERT OR REPLACE INTO channel_settings (user_id, permissions) VALUES (?, ?)",
                (self.member.id, json.dumps(permissions))
            )
            await db.commit()

        status = {
            "permit": "permitted",
            "reject": "rejected",
            "force_ptt": "PTT enabled",
            "disable_ptt": "PTT disabled"
        }.get(self.action, "applied")

        await interaction.response.send_message(f"Selected users have been {status} in your channel.", ephemeral=True)
        logger.info(f"{self.member.display_name} {status} users: {selected_user_ids} in channel '{channel.name}'.")

class SelectRoleView(View):
    """
    View to select multiple roles.
    """
    def __init__(self, bot, member, action):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.action = action

        self.role_select = RoleSelect(
            placeholder="Select Roles",
            min_values=1,
            max_values=25,
            custom_id="role_select"
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)

    async def role_select_callback(self, interaction: Interaction):
        selected_roles = self.role_select.values
        selected_role_ids = [role.id for role in selected_roles]
        channel = await self.bot.get_cog('voice')._get_user_channel(self.member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        targets = [{'type': 'role', 'id': role_id} for role_id in selected_role_ids]

        # Apply permissions
        try:
            await apply_permissions_changes(channel, {'action': self.action, 'targets': targets})
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Update database permissions
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT permissions FROM channel_settings WHERE user_id = ?",
                (self.member.id,)
            )
            settings_row = await cursor.fetchone()
            permissions = {}
            if settings_row and settings_row[0]:
                permissions = json.loads(settings_row[0])

            if 'permissions' not in permissions:
                permissions['permissions'] = []

            permissions['permissions'].append({'action': self.action, 'targets': targets})

            await db.execute(
                "INSERT OR REPLACE INTO channel_settings (user_id, permissions) VALUES (?, ?)",
                (self.member.id, json.dumps(permissions))
            )
            await db.commit()

        status = {
            "permit": "permitted",
            "reject": "rejected",
            "force_ptt": "PTT enabled",
            "disable_ptt": "PTT disabled"
        }.get(self.action, "applied")

        await interaction.response.send_message(f"Selected roles have been {status} in your channel.", ephemeral=True)
        logger.info(f"{self.member.display_name} {status} roles: {selected_role_ids} in channel '{channel.name}'.")

class PTTSelectView(View):
    """
    View to select whether to enable or disable PTT.
    """
    def __init__(self, bot, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member

        self.ptt_select = Select(
            placeholder="Enable or Disable PTT",
            min_values=1,
            max_values=1,
            options=[
                SelectOption(label="Enable PTT", value="enable", description="Force users/roles to use PTT"),
                SelectOption(label="Disable PTT", value="disable", description="Allow users/roles to use voice activation"),
            ]
        )
        self.ptt_select.callback = self.ptt_select_callback
        self.add_item(self.ptt_select)

    async def ptt_select_callback(self, interaction: Interaction):
        enable = True if self.ptt_select.values[0] == "enable" else False
        # Now proceed to select target type
        view = TargetTypeSelectView(self.bot, self.member, action="ptt", enable=enable)
        await interaction.response.edit_message(content="Choose the type of target you want to apply the PTT setting to:", view=view)