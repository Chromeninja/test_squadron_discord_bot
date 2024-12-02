# helpers/views.py

import discord
from discord.ui import View, Select, Button, UserSelect, RoleSelect
from discord import SelectOption, Interaction
import json
from helpers.permissions_helper import apply_permissions_changes
from helpers.embeds import create_token_embed, create_error_embed, create_success_embed, create_cooldown_embed
from helpers.token_manager import generate_token, token_store
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.modals import (
    HandleModal,
    NameModal,
    LimitModal,
    CloseChannelConfirmationModal,
    ResetSettingsConfirmationModal
)
from helpers.logger import get_logger
from helpers.database import Database
from helpers.voice_utils import get_user_channel, get_user_game_name, update_channel_settings, safe_edit_channel

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
        super().__init__(timeout=None)  # Set timeout to None for persistence
        self.bot = bot

        # Add "Get Token" button with custom_id
        self.get_token_button = Button(
            label="Get Token",
            style=discord.ButtonStyle.success,
            custom_id="verification_get_token_button"  # Unique custom_id
        )
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        # Add "Verify" button with custom_id
        self.verify_button = Button(
            label="Verify",
            style=discord.ButtonStyle.primary,
            custom_id="verification_verify_button"  # Unique custom_id
        )
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

    async def get_token_button_callback(self, interaction: Interaction):
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
            logger.info(f"Sent verification token to user '{member.display_name}'.")
        except Exception as e:
            logger.exception(f"Failed to send verification token to user '{member.display_name}': {e}", extra={'user_id': member.id})

    async def verify_button_callback(self, interaction: Interaction):
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
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

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
                SelectOption(
                    label="Reset",
                    value="reset",
                    description="Reset your channel settings to default",
                    emoji="🔄"
                ),
                SelectOption(
                    label="Close",
                    value="close",
                    description="Close your voice channel",
                    emoji="❌"
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
                    label="PTT",
                    value="ptt",
                    description="Manage PTT settings",
                    emoji="🎙️"
                ),
            ]
        )
        self.channel_permissions_select.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensures that only the owner can interact with this view.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You cannot interact with this.", ephemeral=True)
            return False
        return True

    async def _check_ownership(self, interaction: Interaction) -> bool:
        """
        Ensures the user is the owner of the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return False
        return True

    async def channel_settings_callback(self, interaction: Interaction):
        if not await self._check_ownership(interaction):
            return

        selected = self.channel_settings_select.values[0]
        if selected == "name":
            modal = NameModal(self.bot)
            await interaction.response.send_modal(modal)
        elif selected == "limit":
            modal = LimitModal(self.bot)
            await interaction.response.send_modal(modal)
        elif selected == "game":
            channel = await get_user_channel(self.bot, interaction.user)
            if not channel:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return

            game_name = get_user_game_name(interaction.user)
            if not game_name:
                await interaction.response.send_message("You are not currently playing a game.", ephemeral=True)
                return

            # Update channel name to game name with rate limiting
            try:
                await safe_edit_channel(channel, name=game_name[:32])  # Ensure name is within 32 characters

                # Update settings using the helper function
                await update_channel_settings(interaction.user.id, channel_name=game_name)

                embed = discord.Embed(
                    description=f"Channel name has been set to your current game: **{game_name}**.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"{interaction.user.display_name} set their channel name to game: {game_name}.")
            except Exception as e:
                logger.exception(f"Failed to set channel name to game: {e}")
                embed = create_error_embed("Failed to set channel name to your current game. Please try again.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif selected == "reset":
            await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot))
        elif selected == "close":
            await interaction.response.send_modal(CloseChannelConfirmationModal(self.bot))
        else:
            await interaction.response.send_message("Unknown option selected.", ephemeral=True)

    async def channel_permissions_callback(self, interaction: Interaction):
        if not await self._check_ownership(interaction):
            return

        selected = self.channel_permissions_select.values[0]
        if selected in ["permit", "reject"]:
            action = selected
            view = TargetTypeSelectView(self.bot, action=action)
            await interaction.response.send_message("Choose the type of target you want to apply the action to:", view=view, ephemeral=True)
        elif selected == "ptt":
            # Send a view to select enable or disable PTT
            view = PTTSelectView(self.bot)
            await interaction.response.send_message("Do you want to enable or disable PTT?", view=view, ephemeral=True)
        elif selected in ["lock", "unlock"]:
            lock = True if selected == "lock" else False
            channel = await get_user_channel(self.bot, interaction.user)
            if not channel:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return

            # Define permission change
            action = 'lock' if lock else 'unlock'

            permission_change = {
                'action': action,
                'targets': [{'type': 'role', 'id': channel.guild.default_role.id}]
            }

            # Apply permissions with batching and rate limiting
            try:
                await apply_permissions_changes(channel, permission_change)
            except Exception as e:
                logger.error(f"Failed to apply permission '{action}' to channel '{channel.name}': {e}")
                await interaction.response.send_message(f"Failed to {'lock' if lock else 'unlock'} your voice channel.", ephemeral=True)
                return

            # Update settings using the helper function
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT permissions FROM channel_settings WHERE user_id = ?",
                    (interaction.user.id,)
                )
                settings_row = await cursor.fetchone()
                if settings_row and settings_row[0]:
                    permissions = json.loads(settings_row[0])
                    if not isinstance(permissions, dict):
                        permissions = {}
                else:
                    permissions = {}

                permissions['lock'] = lock

                await update_channel_settings(interaction.user.id, permissions=permissions)

            status = "locked" if lock else "unlocked"
            await interaction.response.send_message(f"Your voice channel has been {status}.", ephemeral=True)
            logger.info(f"{interaction.user.display_name} {status} their voice channel.")
        else:
            await interaction.response.send_message("Unknown option selected.", ephemeral=True)

class TargetTypeSelectView(View):
    """
    View to select the type of target (user or role).
    """
    def __init__(self, bot, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
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

    async def _check_ownership(self, interaction: Interaction):
        """
        Ensures the user is the owner of the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return False
        return True
    
    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return False
        return True

    async def target_type_callback(self, interaction: Interaction):
        selected_type = self.target_type_select.values[0]
        if selected_type == "user":
            view = SelectUserView(self.bot, self.action, enable=self.enable)
            await interaction.response.edit_message(content="Select users to apply the action:", view=view)
        elif selected_type == "role":
            view = SelectRoleView(self.bot, self.action, enable=self.enable)
            await interaction.response.edit_message(content="Select roles to apply the action:", view=view)
        else:
            await interaction.response.send_message("Unknown target type selected.", ephemeral=True)

class SelectUserView(View):
    """
    View to select multiple users and apply permissions or actions such as PTT.
    """
    def __init__(self, bot, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action
        self.enable = enable  # For PTT action

        self.user_select = UserSelect(
            placeholder="Select Users",
            min_values=1,
            max_values=25,
            custom_id="user_select"
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        selected_users = self.user_select.values
        selected_user_ids = [user.id for user in selected_users]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        targets = [{'type': 'user', 'id': user_id} for user_id in selected_user_ids]

        # Prepare permission change dictionary
        if self.action == "ptt":
            permission_change = {'action': self.action, 'targets': targets, 'enable': self.enable}
        else:
            permission_change = {'action': self.action, 'targets': targets}

        # Apply permissions with batching and rate limiting
        try:
            await apply_permissions_changes(channel, permission_change)
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Update database permissions
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT permissions FROM channel_settings WHERE user_id = ?",
                (interaction.user.id,)
            )
            settings_row = await cursor.fetchone()
            if settings_row and settings_row[0]:
                existing_permissions = json.loads(settings_row[0])
                if not isinstance(existing_permissions, dict):
                    existing_permissions = {}
            else:
                existing_permissions = {}

            if 'permissions' not in existing_permissions:
                existing_permissions['permissions'] = []

            if self.action == "ptt":
                existing_permissions['ptt'] = existing_permissions.get('ptt', [])
                existing_permissions['ptt'].append({'targets': targets, 'enable': self.enable})
            else:
                existing_permissions['permissions'].append({'action': self.action, 'targets': targets})

            await update_channel_settings(interaction.user.id, permissions=existing_permissions)

        # Determine status message based on action
        if self.action == "ptt":
            status = "PTT enabled" if self.enable else "PTT disabled"
        else:
            status = {
                "permit": "permitted",
                "reject": "rejected",
            }.get(self.action, "applied")

        await interaction.response.send_message(f"Selected users have been {status} in your channel.", ephemeral=True)
        logger.info(f"{interaction.user.display_name} {status} users: {selected_user_ids} in channel '{channel.name}'.")

class SelectRoleView(View):
    """
    View to select multiple roles.
    """
    def __init__(self, bot, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action
        self.enable = enable  # For PTT action

        self.role_select = RoleSelect(
            placeholder="Select Roles",
            min_values=1,
            max_values=25,
            custom_id="role_select"
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return False
        return True

    async def role_select_callback(self, interaction: Interaction):
        selected_roles = self.role_select.values
        selected_role_ids = [role.id for role in selected_roles]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        targets = [{'type': 'role', 'id': role_id} for role_id in selected_role_ids]

        # Prepare permission change dictionary
        if self.action == "ptt":
            permission_change = {'action': self.action, 'targets': targets, 'enable': self.enable}
        else:
            permission_change = {'action': self.action, 'targets': targets}

        # Apply permissions with batching and rate limiting
        try:
            await apply_permissions_changes(channel, permission_change)
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Update database permissions
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT permissions FROM channel_settings WHERE user_id = ?",
                (interaction.user.id,)
            )
            settings_row = await cursor.fetchone()
            if settings_row and settings_row[0]:
                existing_permissions = json.loads(settings_row[0])
                if not isinstance(existing_permissions, dict):
                    existing_permissions = {}
            else:
                existing_permissions = {}

            if 'permissions' not in existing_permissions:
                existing_permissions['permissions'] = []

            if self.action == "ptt":
                existing_permissions['ptt'] = existing_permissions.get('ptt', [])
                existing_permissions['ptt'].append({'targets': targets, 'enable': self.enable})
            else:
                existing_permissions['permissions'].append({'action': self.action, 'targets': targets})

            await update_channel_settings(interaction.user.id, permissions=existing_permissions)

        status = {
            "permit": "permitted",
            "reject": "rejected",
            "ptt": "PTT settings updated"
        }.get(self.action, "applied")

        await interaction.response.send_message(f"Selected roles have been {status} in your channel.", ephemeral=True)
        logger.info(f"{interaction.user.display_name} {status} roles: {selected_role_ids} in channel '{channel.name}'.")

class PTTSelectView(View):
    """
    View to select whether to enable or disable PTT.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

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

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return False
        return True

    async def ptt_select_callback(self, interaction: Interaction):
        enable = True if self.ptt_select.values[0] == "enable" else False
        # Now proceed to select target type
        view = TargetTypeSelectView(self.bot, action="ptt", enable=enable)
        await interaction.response.edit_message(content="Choose the type of target you want to apply the PTT setting to:", view=view)
