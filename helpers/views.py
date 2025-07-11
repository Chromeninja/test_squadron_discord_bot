# helpers/views.py
"""
Interactive Views Module

This module contains all the interactive UI components (buttons, selects, and modals)
used for verification, channel settings, permit/reject actions, and feature toggles.
These views interact with other helper modules to perform operations such as sending
messages, applying permission changes, and updating channel settings.
"""

import discord
from discord.ui import View, Select, Button, UserSelect
from discord import SelectOption, Interaction

from helpers.discord_api import send_message, edit_channel
from helpers.embeds import create_token_embed, create_cooldown_embed
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
    fetch_channel_settings,
    format_channel_settings,
    set_voice_feature_setting,
    apply_voice_feature_toggle,
    create_voice_settings_embed,
)
from helpers.permissions_helper import apply_permissions_changes, store_permit_reject_in_db
from config.config_loader import ConfigLoader

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Custom select for roles with optional filtering based on allowed role IDs.
# If allowed_roles is provided (a list of role IDs), only roles in that list will be displayed.
# Otherwise, all roles in the guild will be shown.
# --------------------------------------------------------------------------
class FilteredRoleSelect(Select):
    def __init__(
        self,
        *,
        allowed_roles: list = None,
        placeholder: str = "Select role(s)",
        min_values: int = 1,
        max_values: int = 25,
        custom_id: str = None,
        **kwargs,
    ):
        base = "filtered_role_select_"
        if custom_id is None or len(custom_id) < len(base):
            extra = "x" * (25 - len(base))
            custom_id = base + extra
        super().__init__(placeholder=placeholder, min_values=min_values, max_values=max_values, options=[], custom_id=custom_id, **kwargs)
        self.allowed_roles = allowed_roles

    def refresh_options(self, guild: discord.Guild) -> None:
        if self.allowed_roles is None:
            filtered_options = [
                SelectOption(label=role.name, value=str(role.id))
                for role in guild.roles
            ]
        else:
            filtered_options = [
                SelectOption(label=role.name, value=str(role.id))
                for role in guild.roles if role.id in self.allowed_roles
            ]
        if not filtered_options:
            logger.warning("FilteredRoleSelect: No matching roles found; adding fallback option.")
            filtered_options = [SelectOption(label="No selectable roles available", value="no_selectable_roles_available")]
            self.disabled = True
        else:
            self.disabled = False
        self.options = filtered_options
        logger.debug(f"FilteredRoleSelect options refreshed: {[opt.label for opt in self.options]}")

# -------------------------
# Verification Buttons
# -------------------------
class VerificationView(View):
    """
    View containing interactive buttons for the verification process.
    
    Contains two buttons:
      - Get Token: Generates and sends a verification token.
      - Verify: Opens a modal to collect the user's RSI handle.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

        self.get_token_button = Button(
            label="Get Token",
            style=discord.ButtonStyle.success,
            custom_id="verification_get_token_button"
        )
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        self.verify_button = Button(
            label="Verify",
            style=discord.ButtonStyle.primary,
            custom_id="verification_verify_button"
        )
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

        self.recheck_button = Button(
            label="Re-Check",
            style=discord.ButtonStyle.secondary,
            custom_id="verification_recheck_button"
        )
        self.recheck_button.callback = self.recheck_button_callback
        self.add_item(self.recheck_button)

    async def get_token_button_callback(self, interaction: Interaction):
        """
        Callback for the 'Get Token' button.
        
        Checks rate limits, generates a token, logs the attempt,
        and sends an embed with the token information.
        """
        member = interaction.user
        rate_limited, wait_until = await check_rate_limit(member.id, "verification")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        token = generate_token(member.id)
        expires_at = token_store[member.id]['expires_at']
        expires_unix = int(expires_at)
        await log_attempt(member.id, "verification")

        embed = create_token_embed(token, expires_unix)
        try:
            await send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info(f"Sent verification token to user '{member.display_name}'.")
        except Exception as e:
            logger.exception(f"Failed to send verification token to user '{member.display_name}': {e}", extra={'user_id': member.id})

    async def verify_button_callback(self, interaction: Interaction):
        """
        Callback for the 'Verify' button.
        
        Checks rate limits and, if permitted, sends the HandleModal for user verification.
        """
        member = interaction.user
        rate_limited, wait_until = await check_rate_limit(member.id, "verification")
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

        modal = HandleModal(self.bot)
        await interaction.response.send_modal(modal)

    async def recheck_button_callback(self, interaction: Interaction):
        verification_cog = self.bot.get_cog("VerificationCog")
        if verification_cog:
            await verification_cog.recheck_button(interaction)
        else:
            # Log a warning and inform the user
            import logging
            logging.warning("VerificationCog is missing. Cannot process recheck_button.")
            await interaction.response.send_message(
                "Verification system is currently unavailable. Please try again later.",
                ephemeral=True
            )

# -------------------------
# Channel Settings + Permissions
# -------------------------
class ChannelSettingsView(View):
    """
    Main view for channel settings.

    Contains two dropdown menus:
      - Channel Settings: Options include Name, Limit, Game, List, and Reset.
      - Channel Permissions: Options include Lock, Unlock, Permit, Reject, PTT, Kick, Priority Speaker, and Soundboard.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

        self.channel_settings_select = Select(
            placeholder="Channel Settings",
            min_values=1,
            max_values=1,
            options=[
                SelectOption(label="Name", value="name", description="Change the name of the channel", emoji="✏️"),
                SelectOption(label="Limit", value="limit", description="Limit how many users can join", emoji="🔢"),
                SelectOption(label="Game", value="game", description="Set channel name to your current game", emoji="🎮"),
                SelectOption(label="List", value="list", description="View current channel settings and permissions", emoji="📜"),
                SelectOption(label="Reset", value="reset", description="Reset your channel settings to default", emoji="🔄"),
            ]
        )
        self.channel_settings_select.callback = self.channel_settings_callback
        self.add_item(self.channel_settings_select)

        self.channel_permissions_select_1 = Select(
            placeholder="Channel Permissions (1/2)",
            min_values=1,
            max_values=1,
            custom_id="channel_permissions_select_1",
            options=[
                SelectOption(label="Lock", value="lock", description="Lock the channel", emoji="🔒"),
                SelectOption(label="Unlock", value="unlock", description="Unlock the channel", emoji="🔓"),
                SelectOption(label="Permit", value="permit", description="Permit users/roles to join", emoji="✅"),
                SelectOption(label="Reject", value="reject", description="Reject users/roles from joining", emoji="🚫"),
                SelectOption(label="PTT", value="ptt", description="Manage PTT settings", emoji="🎙️"),
            ]
        )
        self.channel_permissions_select_1.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select_1)

        self.channel_permissions_select_2 = Select(
            placeholder="Channel Permissions (2/2)",
            min_values=1,
            max_values=1,
            custom_id="channel_permissions_select_2",
            options=[
                SelectOption(label="Kick", value="kick", description="Kick a user from your channel", emoji="👢"),
                SelectOption(label="Priority Speaker", value="priority_speaker", description="Grant/revoke priority speaker", emoji="📢"),
                SelectOption(label="Soundboard", value="soundboard", description="Enable/disable soundboard", emoji="🔊"),
            ]
        )
        self.channel_permissions_select_2.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select_2)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensure that the interacting user owns a voice channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You cannot interact with this. You don't own a channel.", ephemeral=True)
            return False
        return True

    async def channel_settings_callback(self, interaction: Interaction):
        """
        Handle selections from the channel settings dropdown.

        Depending on the selection, open the appropriate modal or display current settings.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        selected = self.channel_settings_select.values[0]

        try:
            if selected == "name":
                modal = NameModal(self.bot)
                await interaction.response.send_modal(modal)
            elif selected == "limit":
                modal = LimitModal(self.bot)
                await interaction.response.send_modal(modal)
            elif selected == "game":
                member = interaction.guild.get_member(interaction.user.id)
                if not member:
                    await send_message(interaction, "Unable to retrieve your member data.", ephemeral=True)
                    return
                game_name = get_user_game_name(member)
                if not game_name:
                    await send_message(interaction, "You are not currently playing a game.", ephemeral=True)
                    return

                await edit_channel(channel, name=game_name[:32])
                await update_channel_settings(interaction.user.id, channel_name=game_name)
                e = discord.Embed(
                    description=f"Channel name set to your current game: **{game_name}**.",
                    color=discord.Color.green()
                )
                await send_message(interaction, "", embed=e, ephemeral=True)
            elif selected == "list":
                settings = await fetch_channel_settings(self.bot, interaction)
                if not settings:
                    return
                formatted = format_channel_settings(settings, interaction)
                embed = create_voice_settings_embed(
                    settings=settings,
                    formatted=formatted,
                    title="Channel Settings & Permissions",
                    footer="Use /voice commands or the dropdown menu to adjust these settings."
                )
                await send_message(interaction, "", embed=embed, ephemeral=True)
            elif selected == "reset":
                await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot))
            else:
                await send_message(interaction, "Unknown option selected.", ephemeral=True)

            # Update the original message to preserve the view.
            await interaction.message.edit(view=self)
        except Exception as e:
            logger.exception(f"Error in channel_settings_callback: {e}")
            await send_message(interaction, "An error occurred.", ephemeral=True)

    async def channel_permissions_callback(self, interaction: Interaction):
        """
        Handle selections from the channel permissions dropdown.

        Depending on the selection, either display an additional view or apply permission changes immediately.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        dropdown_trigger = interaction.data['custom_id']
        if dropdown_trigger == "channel_permissions_select_1":
            selected = self.channel_permissions_select_1.values[0]
        else:
            selected = self.channel_permissions_select_2.values[0]

        if selected in ["permit", "reject"]:
            view = TargetTypeSelectView(self.bot, action=selected)
            await send_message(
                interaction,
                f"Choose the type of target you want to {selected}:",
                view=view,
                ephemeral=True
            )
        elif selected in ["lock", "unlock"]:
            lock = (selected == "lock")
            permission_change = {
                'action': selected,
                'targets': [{'type': 'role', 'id': channel.guild.default_role.id}]
            }
            await apply_permissions_changes(channel, permission_change)
            await update_channel_settings(interaction.user.id, lock=1 if lock else 0)
            status = "locked" if lock else "unlocked"
            await send_message(interaction, f"Your voice channel has been {status}.", ephemeral=True)
        elif selected == "ptt":
            view = FeatureToggleView(self.bot, feature_name="ptt")
            await send_message(interaction, "Do you want to enable or disable PTT?", view=view, ephemeral=True)
        elif selected == "kick":
            view = KickUserSelectView(self.bot)
            await send_message(interaction, "Select a user to kick:", view=view, ephemeral=True)
        elif selected == "priority_speaker":
            view = FeatureToggleView(self.bot, feature_name="priority_speaker", no_everyone=True)
            await send_message(interaction, "Enable or disable Priority Speaker?", view=view, ephemeral=True)
        elif selected == "soundboard":
            view = FeatureToggleView(self.bot, feature_name="soundboard")
            await send_message(interaction, "Enable or disable Soundboard?", view=view, ephemeral=True)
        else:
            await send_message(interaction, "Unknown option.", ephemeral=True)

        try:
            await interaction.message.edit(view=self)
        except discord.errors.NotFound:
            pass

# ----------------------------
# Kick User Selection View
# ----------------------------
class KickUserSelectView(View):
    """
    View that allows the channel owner to select a user to kick,
    with an optional button to also reject them from rejoining.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

        self.user_select = UserSelect(
            placeholder="Select user to kick",
            min_values=1,
            max_values=1
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

        self.reject_button = Button(
            label="Also Reject from Rejoining",
            style=discord.ButtonStyle.danger
        )
        self.reject_button.callback = self.reject_button_callback
        self.add_item(self.reject_button)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensures the user owns a channel before interaction.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        """
        Callback for user selection. Verifies the selected user is in the channel
        and then kicks them.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if not self.user_select.values:
            await send_message(interaction, "No user selected.", ephemeral=True)
            return

        target_user = self.user_select.values[0]
        if target_user not in channel.members:
            await send_message(interaction, f"{target_user.display_name} is not in your channel.", ephemeral=True)
            return

        try:
            await target_user.move_to(None)
            await send_message(interaction, f"{target_user.display_name} was kicked from your channel.", ephemeral=True)
        except Exception as e:
            await send_message(interaction, f"Failed to kick user: {e}", ephemeral=True)

    async def reject_button_callback(self, interaction: Interaction):
        """
        Callback for rejecting a user after kicking them.
        Updates the channel's permission overwrites to prevent the user from rejoining.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if not self.user_select.values:
            await send_message(interaction, "No user selected for reject.", ephemeral=True)
            return

        target_user = self.user_select.values[0]
        try:
            await target_user.move_to(None)
        except Exception as e:
            await send_message(interaction, f"Failed to kick user: {e}", ephemeral=True)
            return

        overwrites = channel.overwrites.copy()
        ow = overwrites.get(target_user, discord.PermissionOverwrite())
        ow.connect = False
        overwrites[target_user] = ow

        try:
            await edit_channel(channel, overwrites=overwrites)
            await send_message(interaction, f"{target_user.display_name} was kicked and rejected from rejoining.", ephemeral=True)
        except Exception as e:
            await send_message(interaction, f"Kicked but failed to reject rejoining: {e}", ephemeral=True)

# ----------------------------
# Unified Feature Toggle Views
# (Handles PTT, Priority Speaker, and Soundboard toggles)
# ----------------------------
class FeatureToggleView(View):
    """
    A unified view for toggling a feature (PTT, Priority Speaker, or Soundboard).

    Presents a select menu to choose between enabling or disabling the feature.
    The 'no_everyone' flag can be set to exclude the 'Everyone' option.
    """
    def __init__(self, bot, feature_name: str, no_everyone: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.feature_name = feature_name
        self.no_everyone = no_everyone

        self.toggle_select = Select(
            placeholder=f"Enable or Disable {feature_name.title()}?",
            options=[
                SelectOption(label="Enable", value="enable"),
                SelectOption(label="Disable", value="disable"),
            ],
            min_values=1,
            max_values=1
        )
        self.toggle_select.callback = self.toggle_select_callback
        self.add_item(self.toggle_select)

    async def toggle_select_callback(self, interaction: Interaction):
        """
        Callback for the toggle select.
        Determines if the feature should be enabled or disabled and shows the target selection view.
        """
        enable = (self.toggle_select.values[0] == "enable")
        view = FeatureTargetView(self.bot, self.feature_name, enable, self.no_everyone)
        await send_message(
            interaction,
            f"Select who to {'enable' if enable else 'disable'} {self.feature_name} for:",
            ephemeral=True,
            view=view
        )

class FeatureTargetView(View):
    """
    A view that lets the user choose a target type (User, Role, or Everyone) for the feature toggle.
    """
    def __init__(self, bot, feature_name: str, enable: bool, no_everyone: bool):
        super().__init__(timeout=None)
        self.bot = bot
        self.feature_name = feature_name
        self.enable = enable
        self.no_everyone = no_everyone

        options = [
            SelectOption(label="User", value="user"),
            SelectOption(label="Role", value="role"),
        ]
        if not no_everyone:
            options.append(SelectOption(label="Everyone", value="everyone"))

        self.target_select = Select(
            placeholder="User, Role, or Everyone?",
            options=options,
            min_values=1,
            max_values=1
        )
        self.target_select.callback = self.target_select_callback
        self.add_item(self.target_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensures the interacting user owns a channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def target_select_callback(self, interaction: Interaction):
        """
        Callback for target selection.
        
        If 'everyone' is selected, applies the feature toggle immediately;
        otherwise, displays the appropriate user or role select view.
        """
        selection = self.target_select.values[0]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if selection == "everyone":
            target = channel.guild.default_role
            target_type = "everyone"
            target_id = 0
            await set_voice_feature_setting(self.feature_name, interaction.user.id, target_id, target_type, self.enable)
            await apply_voice_feature_toggle(channel, self.feature_name, target, self.enable)
            msg = f"{self.feature_name.replace('_', ' ').title()} has been {'enabled' if self.enable else 'disabled'} for everyone."
            await send_message(interaction, msg, ephemeral=True)
        elif selection == "user":
            view = FeatureUserSelectView(self.bot, self.feature_name, self.enable)
            await send_message(
                interaction,
                f"Select user(s) to {'enable' if self.enable else 'disable'} {self.feature_name} for:",
                ephemeral=True,
                view=view
            )
        else:  # 'role'
            if self.feature_name in ["permit", "reject"]:
                view = TargetTypeSelectView(self.bot, action=self.feature_name)
            else:
                view = FeatureRoleSelectView(self.bot, self.feature_name, self.enable)
            await send_message(
                interaction,
                f"Select role(s) to {'enable' if self.enable else 'disable'} {self.feature_name} for:",
                ephemeral=True,
                view=view
            )
        try:
            await interaction.message.edit(view=None)
        except discord.errors.NotFound:
            pass

class FeatureUserSelectView(View):
    """
    A view for selecting one or more users for a feature toggle (PTT, Priority Speaker, or Soundboard).
    """
    def __init__(self, bot, feature_name: str, enable: bool):
        super().__init__(timeout=None)
        self.bot = bot
        self.feature_name = feature_name
        self.enable = enable

        self.user_select = UserSelect(
            placeholder="Select user(s)",
            min_values=1,
            max_values=25
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Checks that the interacting user owns a channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        """
        Callback for when users are selected.
        Stores the feature setting for each selected user and applies it to the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        for user in self.user_select.values:
            await set_voice_feature_setting(self.feature_name, interaction.user.id, user.id, "user", self.enable)
            await apply_voice_feature_toggle(channel, self.feature_name, user, self.enable)

        msg = f"{self.feature_name.title()} {'enabled' if self.enable else 'disabled'} for selected user(s)."
        await send_message(interaction, msg, ephemeral=True)
        try:
            await interaction.message.edit(view=None)
        except discord.errors.NotFound:
            pass

class FeatureRoleSelectView(View):
    """
    A view for selecting one or more roles for a feature toggle (PTT, Priority Speaker, or Soundboard).
    """
    def __init__(self, bot, feature_name: str, enable: bool):
        super().__init__(timeout=None)
        self.bot = bot
        self.feature_name = feature_name
        self.enable = enable
        
        # Retrieve allowed role IDs from config
        config = ConfigLoader.load_config()
        allowed_roles = config.get("selectable_roles", [])
        
        self.role_select = FilteredRoleSelect(
            allowed_roles=allowed_roles,
            placeholder="Select role(s)",
            min_values=1,
            max_values=1,
            custom_id="feature_role_select_" + "z" * 10
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)
        if self.bot.guilds:
            self.role_select.refresh_options(self.bot.guilds[0])

    async def interaction_check(self, interaction: Interaction) -> bool:
        self.role_select.refresh_options(interaction.guild)
        return True

    async def role_select_callback(self, interaction: Interaction) -> None:
        """
        Callback for role selection.
        Instead of applying "permit/reject", it now properly enables/disables the selected feature.
        """
        try:
            channel = await get_user_channel(self.bot, interaction.user)
            if not channel:
                await send_message(interaction, "You don't own a channel.", ephemeral=True)
                return
            targets = []
            for role_id_str in self.role_select.values:
                try:
                    role_id = int(role_id_str)
                except ValueError:
                    await send_message(interaction, "No selectable roles available.", ephemeral=True)
                    return
                targets.append({"type": "role", "id": role_id})

                # Store the feature setting in the database for future reference
                await set_voice_feature_setting(
                    feature=self.feature_name,
                    user_id=interaction.user.id,
                    target_id=role_id,
                    target_type="role",
                    enable=self.enable
                )

            # Apply the actual permission change to the channel
            for target in targets:
                if role := interaction.guild.get_role(target["id"]):
                    await apply_voice_feature_toggle(channel, self.feature_name, role, self.enable)

            msg = f"{self.feature_name.replace('_', ' ').title()} has been {'enabled' if self.enable else 'disabled'} for selected role(s)."
            await send_message(interaction, msg, ephemeral=True)

            # Remove the selection UI after it's done
            try:
                await interaction.message.edit(view=None)
            except discord.errors.NotFound:
                pass
        except Exception as e:
            logger.exception(f"Error in FeatureRoleSelectView callback: {e}", extra={'user_id': interaction.user.id})

# ======================================
# Permit/Reject Classes
# ======================================
class TargetTypeSelectView(View):
    """
    View to select the target type for permit/reject actions.
    
    Only offers 'User' and 'Role' options.
    """
    def __init__(self, bot, action: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action

        options = [
            SelectOption(label="User", value="user", description="Select specific user(s)"),
            SelectOption(label="Role", value="role", description="Select a role"),
        ]
        self.select = Select(
            placeholder="Select Target Type",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensures the interacting user owns a channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: Interaction):
        """
        Callback for target type selection.
        Depending on the selection, shows either a user or role selection view.
        """
        choice = self.select.values[0]
        if choice == "user":
            view = SelectUserView(self.bot, action=self.action)
            await send_message(interaction, f"Select user(s) to {self.action}:", ephemeral=True, view=view)
        else:
            view = SelectRoleView(self.bot, action=self.action)
            await send_message(interaction, f"Select role(s) to {self.action}:", ephemeral=True, view=view)
        try:
            await interaction.message.edit(view=None)
        except discord.errors.NotFound:
            pass

class SelectUserView(View):
    """
    View for selecting multiple users to apply permit/reject actions.
    """
    def __init__(self, bot, action: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action
        self.user_select = UserSelect(
            placeholder="Select user(s)",
            min_values=1,
            max_values=25
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensure the user owns a channel before interacting.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        """
        Callback for when users are selected.
        Stores the permit/reject settings in the database and applies the changes to the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        targets = []
        for user in self.user_select.values:
            targets.append({"type": "user", "id": user.id})
            await store_permit_reject_in_db(interaction.user.id, user.id, "user", self.action)
        permission_change = {
            "action": self.action,
            "targets": targets
        }
        await apply_permissions_changes(channel, permission_change)
        await send_message(interaction, f"Selected user(s) have been {self.action}ed.", ephemeral=True)
        try:
            await interaction.message.edit(view=None)
        except discord.errors.NotFound:
            pass

class SelectRoleView(View):
    """
    View for selecting multiple roles to apply permit/reject actions.
    """
    def __init__(self, bot, action: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.action = action
        config = ConfigLoader.load_config()
        allowed_roles = config.get("selectable_roles", [])
        self.role_select = FilteredRoleSelect(
            allowed_roles=allowed_roles,
            placeholder="Select role(s)",
            min_values=1,
            max_values=1,
            custom_id="permit_role_select_" + "z" * 10
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)
        if self.bot.guilds:
            self.role_select.refresh_options(self.bot.guilds[0])

    async def interaction_check(self, interaction: Interaction) -> bool:
        self.role_select.refresh_options(interaction.guild)
        return True

    async def role_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        targets = []
        for role_id_str in self.role_select.values:
            try:
                role_id = int(role_id_str)
            except ValueError:
                await send_message(interaction, "No selectable roles available.", ephemeral=True)
                return
            targets.append({"type": "role", "id": role_id})
            await store_permit_reject_in_db(interaction.user.id, role_id, "role", self.action)
        permission_change = {
            "action": self.action,
            "targets": targets
        }
        await apply_permissions_changes(channel, permission_change)
        await send_message(interaction, f"Selected role(s) have been {self.action}ed.", ephemeral=True)
        try:
            await interaction.message.edit(view=None)
        except discord.errors.NotFound:
            pass
