# helpers/views.py

import discord
from discord.ui import View, Select, Button, UserSelect, RoleSelect
from discord import SelectOption, Interaction

from helpers.permissions_helper import apply_permissions_changes
from helpers.embeds import create_token_embed, create_error_embed, create_cooldown_embed
from helpers.token_manager import generate_token, token_store
from helpers.rate_limiter import check_rate_limit, log_attempt
from helpers.modals import (
    HandleModal,
    NameModal,
    LimitModal,
    ResetSettingsConfirmationModal
)
from helpers.logger import get_logger
from helpers.voice_utils import (
    get_user_channel,
    get_user_game_name,
    update_channel_settings,
    set_channel_permission,
    set_ptt_setting
)
from helpers.discord_api import edit_channel, send_message

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
            custom_id="verification_get_token_button"
        )
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        # Add "Verify" button with custom_id
        self.verify_button = Button(
            label="Verify",
            style=discord.ButtonStyle.primary,
            custom_id="verification_verify_button"
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
            await send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        token = generate_token(member.id)
        expires_at = token_store[member.id]['expires_at']
        expires_unix = int(expires_at)
        log_attempt(member.id)

        # Create and send token embed
        embed = create_token_embed(token, expires_unix)

        try:
            await send_message(interaction, "", embed=embed, ephemeral=True)
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
            await send_message(interaction, "", embed=embed, ephemeral=True)
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
            await send_message(interaction, "You cannot interact with this.", ephemeral=True)
            return False
        return True

    async def _check_ownership(self, interaction: Interaction) -> bool:
        """
        Ensures the user is the owner of the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
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
                await send_message(interaction, "You don't own a channel.", ephemeral=True)
                return

            # Get the Member object from the interaction
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                await send_message(interaction, "Unable to retrieve your member data.", ephemeral=True)
                return
            game_name = get_user_game_name(member)
            if not game_name:
                await send_message(interaction, "You are not currently playing a game.", ephemeral=True)
                return

            # Update channel name to game name with rate limiting
            try:
                await edit_channel(channel, name=game_name[:32])
                await update_channel_settings(interaction.user.id, channel_name=game_name)

                embed = discord.Embed(
                    description=f"Channel name has been set to your current game: **{game_name}**.",
                    color=discord.Color.green()
                )
                await send_message(interaction, "", embed=embed, ephemeral=True)
                logger.info(f"{interaction.user.display_name} set their channel name to game: {game_name}.")
            except Exception as e:
                logger.exception(f"Failed to set channel name to game: {e}")
                embed = create_error_embed("Failed to set channel name to your current game. Please try again.")
                await send_message(interaction, "", embed=embed, ephemeral=True)
        elif selected == "reset":
            await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot))
        else:
            await send_message(interaction, "Unknown option selected.", ephemeral=True)

    async def channel_permissions_callback(self, interaction: Interaction):
        if not await self._check_ownership(interaction):
            return

        selected = self.channel_permissions_select.values[0]
        if selected in ["permit", "reject"]:
            action = selected
            view = TargetTypeSelectView(self.bot, action=action)
            await send_message(interaction,
                "Choose the type of target you want to apply the action to:", view=view, ephemeral=True
            )
        elif selected == "ptt":
            # Send a view to select enable or disable PTT
            view = PTTSelectView(self.bot)
            await send_message(interaction, "Do you want to enable or disable PTT?", view=view, ephemeral=True)
        elif selected in ["lock", "unlock"]:
            lock = True if selected == "lock" else False
            channel = await get_user_channel(self.bot, interaction.user)
            if not channel:
                await send_message(interaction, "You don't own a channel.", ephemeral=True)
                return

            permission_change = {
                'action': 'lock' if lock else 'unlock',
                'targets': [{'type': 'role', 'id': channel.guild.default_role.id}]
            }

            # Apply permissions with batching and rate limiting
            try:
                await apply_permissions_changes(channel, permission_change)
            except Exception as e:
                logger.error(f"Failed to apply permission '{selected}' to channel '{channel.name}': {e}")
                await send_message(interaction,
                    f"Failed to {selected} your voice channel.", ephemeral=True
                )
                return

            # Update the lock state directly
            await update_channel_settings(interaction.user.id, lock=1 if lock else 0)

            status = "locked" if lock else "unlocked"
            await send_message(interaction,f"Your voice channel has been {status}.", ephemeral=True)
            logger.info(f"{interaction.user.display_name} {status} their voice channel.")
        else:
            await send_message(interaction, "Unknown option selected.", ephemeral=True)

class TargetTypeSelectView(View):
    """
    View to select the type of target (user, role, or everyone for PTT only).
    """
    def __init__(self, bot, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action
        self.enable = enable

        options = [
            SelectOption(label="User", value="user", description="Select users to apply the action"),
            SelectOption(label="Role", value="role", description="Select roles to apply the action"),
        ]

        # Add 'Everyone' option only if action is 'ptt'
        if self.action == "ptt":
            options.append(
                SelectOption(label="Everyone", value="everyone", description="Apply to everyone")
            )

        self.target_type_select = Select(
            placeholder="Select Target Type",
            min_values=1,
            max_values=1,
            options=options
        )
        self.target_type_select.callback = self.target_type_callback
        self.add_item(self.target_type_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def target_type_callback(self, interaction: Interaction):
        selected_type = self.target_type_select.values[0]

        # If the action is ptt and the user selected "everyone"
        if self.action == "ptt" and selected_type == "everyone":
            # Directly apply PTT to everyone
            member = interaction.user
            channel = await get_user_channel(self.bot, member)
            if not channel:
                await send_message(interaction, "You don't own a channel.", ephemeral=True)
                return

            # Set PTT for everyone in the database
            await set_ptt_setting(member.id, target_id=None, target_type='everyone', ptt_enabled=self.enable)

            # Apply permission changes
            permission_change = {
                'action': 'ptt',
                'targets': [{'type': 'everyone', 'id': None}],
                'enable': self.enable
            }

            try:
                await apply_permissions_changes(channel, permission_change)
                status = "enabled" if self.enable else "disabled"
                await interaction.response.edit_message(
                    content=f"PTT has been {status} for everyone in your channel.", view=None
                )
            except Exception as e:
                await send_message(interaction,f"Failed to apply PTT settings: {e}", ephemeral=True)
            return

        # If the user selected 'user' or 'role' (or action != ptt)
        if selected_type == "user":
            view = SelectUserView(self.bot, self.action, enable=self.enable)
            await interaction.response.edit_message(
                content="Select users to apply the action:", view=view
            )
        elif selected_type == "role":
            view = SelectRoleView(self.bot, self.action, enable=self.enable)
            await interaction.response.edit_message(
                content="Select roles to apply the action:", view=view
            )
        else:
            await send_message(interaction, "Unknown target type selected.", ephemeral=True)

class SelectUserView(View):
    """
    View to select multiple users and apply permissions or actions such as PTT.
    """
    def __init__(self, bot, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
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

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        selected_users = self.user_select.values
        selected_user_ids = [user.id for user in selected_users]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        targets = [{'type': 'user', 'id': user_id} for user_id in selected_user_ids]
        if self.action == "ptt":
            permission_change = {'action': 'ptt', 'targets': targets, 'enable': self.enable}
        else:
            permission_change = {'action': self.action, 'targets': targets}

        try:
            await apply_permissions_changes(channel, permission_change)
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await send_message(interaction, "", embed=embed, ephemeral=True)
            return

        if self.action in ["permit", "reject"]:
            for user_id in selected_user_ids:
                await set_channel_permission(interaction.user.id, user_id, 'user', self.action)
        elif self.action == "ptt":
            for user_id in selected_user_ids:
                await set_ptt_setting(interaction.user.id, user_id, 'user', self.enable)

        if self.action == "ptt":
            status = "PTT enabled" if self.enable else "PTT disabled"
        else:
            status = "permitted" if self.action == "permit" else "rejected"

        await send_message(interaction,
            f"Selected users have been {status} in your channel.", ephemeral=True
        )
        logger.info(
            f"{interaction.user.display_name} {status} users: {selected_user_ids} in channel '{channel.name}'."
        )

class SelectRoleView(View):
    """
    View to select multiple roles.
    """
    def __init__(self, bot, action, enable=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action
        self.enable = enable

        self.role_select = RoleSelect(
            placeholder="Select Roles",
            min_values=1,
            max_values=25,
            custom_id="role_select"
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def role_select_callback(self, interaction: Interaction):
        selected_roles = self.role_select.values
        selected_role_ids = [role.id for role in selected_roles]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        targets = [{'type': 'role', 'id': role_id} for role_id in selected_role_ids]
        if self.action == "ptt":
            permission_change = {'action': 'ptt', 'targets': targets, 'enable': self.enable}
        else:
            permission_change = {'action': self.action, 'targets': targets}

        try:
            await apply_permissions_changes(channel, permission_change)
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await send_message(interaction, "", embed=embed, ephemeral=True)
            return

        if self.action in ["permit", "reject"]:
            for role_id in selected_role_ids:
                await set_channel_permission(interaction.user.id, role_id, 'role', self.action)
        elif self.action == "ptt":
            for role_id in selected_role_ids:
                await set_ptt_setting(interaction.user.id, role_id, 'role', self.enable)

        if self.action == "ptt":
            status = "PTT settings updated"
        else:
            status = "permitted" if self.action == "permit" else "rejected"

        await send_message(interaction,
            f"Selected roles have been {status} in your channel.", ephemeral=True
        )
        logger.info(
            f"{interaction.user.display_name} {status} roles: {selected_role_ids} in channel '{channel.name}'."
        )

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
                SelectOption(label="Enable PTT",  value="enable",  description="Force users/roles to use PTT"),
                SelectOption(label="Disable PTT", value="disable", description="Allow users/roles to use voice activation"),
            ]
        )
        self.ptt_select.callback = self.ptt_select_callback
        self.add_item(self.ptt_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def ptt_select_callback(self, interaction: Interaction):
        enable = (self.ptt_select.values[0] == "enable")
        view = TargetTypeSelectView(self.bot, action="ptt", enable=enable)
        await interaction.response.edit_message(
            content="Choose the type of target you want to apply the PTT setting to:", view=view
        )
