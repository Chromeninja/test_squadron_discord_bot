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
    set_ptt_setting,
    set_priority_speaker_setting,
    set_soundboard_setting,
)
from helpers.discord_api import edit_channel, send_message, edit_message

logger = get_logger(__name__)

class VerificationView(View):
    """
    View containing interactive buttons for the verification process.
    """
    def __init__(self, bot):
        """
        Initializes the VerificationView with buttons.
        """
        super().__init__(timeout=None)  # Set timeout to None for persistence
        self.bot = bot

        # "Get Token" button
        self.get_token_button = Button(
            label="Get Token",
            style=discord.ButtonStyle.success,
            custom_id="verification_get_token_button"
        )
        self.get_token_button.callback = self.get_token_button_callback
        self.add_item(self.get_token_button)

        # "Verify" button
        self.verify_button = Button(
            label="Verify",
            style=discord.ButtonStyle.primary,
            custom_id="verification_verify_button"
        )
        self.verify_button.callback = self.verify_button_callback
        self.add_item(self.verify_button)

    async def get_token_button_callback(self, interaction: Interaction):
        """
        Generates and sends a verification token to the user (ephemeral).
        """
        member = interaction.user
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

        embed = create_token_embed(token, expires_unix)
        try:
            # Ephemeral message so only the user sees it
            await send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info(f"Sent verification token to user '{member.display_name}'.")
        except Exception as e:
            logger.exception(
                f"Failed to send verification token to user '{member.display_name}': {e}",
                extra={'user_id': member.id}
            )

    async def verify_button_callback(self, interaction: Interaction):
        """
        Opens the modal to get RSI handle for verification.
        """
        member = interaction.user
        rate_limited, wait_until = check_rate_limit(member.id)
        if rate_limited:
            embed = create_cooldown_embed(wait_until)
            await send_message(interaction, "", embed=embed, ephemeral=True)
            logger.info("User reached max verification attempts.", extra={'user_id': member.id})
            return

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
                    description="Limit how many users can join",
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

        # Channel Permissions Select Menus (Split into two parts)
        self.channel_permissions_select_1 = Select(
            placeholder="Channel Permissions (1/2)",
            min_values=1,
            max_values=1,
            custom_id="channel_permissions_select_1",
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
        self.channel_permissions_select_1.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select_1)

        self.channel_permissions_select_2 = Select(
            placeholder="Channel Permissions (2/2)",
            min_values=1,
            max_values=1,
            custom_id="channel_permissions_select_2",
            options=[
                SelectOption(
                    label="Mute",
                    value="mute",
                    description="Mute a user in your channel",
                    emoji="🔇"
                ),
                SelectOption(
                    label="Kick",
                    value="kick",
                    description="Kick a user from your channel",
                    emoji="👢"
                ),
                SelectOption(
                    label="Priority Speaker",
                    value="priority_speaker",
                    description="Grant or revoke priority speaker",
                    emoji="📢"
                ),
                SelectOption(
                    label="Soundboard",
                    value="soundboard",
                    description="Enable/disable soundboard",
                    emoji="🔊"
                ),
            ]
        )
        self.channel_permissions_select_2.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select_2)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Ensure only the channel owner can interact
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You cannot interact with this.", ephemeral=True)
            return False
        return True

    async def _check_ownership(self, interaction: Interaction) -> bool:
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def channel_settings_callback(self, interaction: Interaction):
        if not await self._check_ownership(interaction):
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
                channel = await get_user_channel(self.bot, interaction.user)
                if not channel:
                    await send_message(interaction, "You don't own a channel.", ephemeral=True)
                    return

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

                embed = discord.Embed(
                    description=f"Channel name has been set to your current game: **{game_name}**.",
                    color=discord.Color.green()
                )
                await send_message(interaction, "", embed=embed, ephemeral=True)
                logger.info(f"{interaction.user.display_name} set their channel name to game: {game_name}.")
            elif selected == "reset":
                await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot))
            else:
                await send_message(interaction, "Unknown option selected.", ephemeral=True)

            # Reset the dropdown after action
            await interaction.message.edit(view=self)

        except Exception as e:
            logger.exception(f"Error in processing channel settings: {e}")
            await send_message(interaction, "An error occurred while processing your request.", ephemeral=True)

    async def channel_permissions_callback(self, interaction: Interaction):
        if not await self._check_ownership(interaction):
            return

        dropdown_trigger = interaction.data['custom_id']
        if dropdown_trigger == "channel_permissions_select_1":
            selected = self.channel_permissions_select_1.values[0]
        elif dropdown_trigger == "channel_permissions_select_2":
            selected = self.channel_permissions_select_2.values[0]
        else:
            await send_message(interaction, "Unknown dropdown triggered the callback.", ephemeral=True)
            return

        try:
            if selected in ["permit", "reject"]:
                action = selected
                view = TargetTypeSelectView(self.bot, action=action)
                await send_message(
                    interaction,
                    "Choose the type of target you want to apply the action to:",
                    view=view,
                    ephemeral=True
                )
            elif selected == "ptt":
                view = PTTSelectView(self.bot)
                await send_message(
                    interaction,
                    "Do you want to enable or disable PTT?",
                    view=view,
                    ephemeral=True
                )
            elif selected in ["lock", "unlock"]:
                lock = (selected == "lock")
                channel = await get_user_channel(self.bot, interaction.user)
                if not channel:
                    await send_message(interaction, "You don't own a channel.", ephemeral=True)
                    return

                permission_change = {
                    'action': 'lock' if lock else 'unlock',
                    'targets': [{'type': 'role', 'id': channel.guild.default_role.id}]
                }

                await apply_permissions_changes(channel, permission_change)
                await update_channel_settings(interaction.user.id, lock=1 if lock else 0)
                status = "locked" if lock else "unlocked"
                await send_message(
                    interaction,
                    f"Your voice channel has been {status}.",
                    ephemeral=True
                )
                logger.info(f"{interaction.user.display_name} {status} their voice channel.")
            elif selected == "mute":
                view = MuteUserSelectView(self.bot)
                await send_message(
                    interaction,
                    "Select a user to mute:",
                    view=view,
                    ephemeral=True
                )
            elif selected == "kick":
                view = KickUserSelectView(self.bot)
                await send_message(
                    interaction,
                    "Select a user to kick from your channel:",
                    view=view,
                    ephemeral=True
                )
            elif selected == "priority_speaker":
                view = PrioritySpeakerSelectView(self.bot)
                await send_message(
                    interaction,
                    "Do you want to enable or disable Priority Speaker?",
                    view=view,
                    ephemeral=True
                )
            elif selected == "soundboard":
                view = SoundboardSelectView(self.bot)
                await send_message(
                    interaction,
                    "Enable or disable soundboard access?",
                    view=view,
                    ephemeral=True
                )
            else:
                await send_message(interaction, "Unknown option selected.", ephemeral=True)

            # Reset the dropdown after action
            await interaction.message.edit(view=self)

        except Exception as e:
            logger.exception(f"Error in processing channel permissions: {e}")
            await send_message(interaction, "An error occurred while processing your request.", ephemeral=True)

# -----------------------------------------------------------
# Mute, Kick, Priority Speaker, Soundboard, etc.
# -----------------------------------------------------------

class MuteUserSelectView(View):
    """
    Allows selection of exactly one user to mute.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_select = UserSelect(
            placeholder="Select user to mute",
            min_values=1,
            max_values=1
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if not self.user_select.values:
            await send_message(interaction, "No user selected.", ephemeral=True)
            return

        target_user = self.user_select.values[0]
        if target_user not in channel.members:
            await send_message(
                interaction,
                f"{target_user.display_name} is not in your channel.",
                ephemeral=True
            )
            return

        overwrites = channel.overwrites.copy()
        ow = overwrites.get(target_user, discord.PermissionOverwrite())
        ow.speak = False
        overwrites[target_user] = ow

        try:
            await edit_channel(channel, overwrites=overwrites)
            await send_message(
                interaction,
                f"{target_user.display_name} has been muted in your channel.",
                ephemeral=True
            )
        except Exception as e:
            await send_message(
                interaction,
                f"Failed to mute {target_user.display_name}: {e}",
                ephemeral=True
            )


class KickUserSelectView(View):
    """
    Allows selection of exactly one user to kick, with an optional reject toggle.
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

        # Reject toggle
        self.reject_button = Button(
            label="Also Reject from Rejoining",
            style=discord.ButtonStyle.danger
        )
        self.reject_button.callback = self.reject_button_callback
        self.add_item(self.reject_button)

    async def interaction_check(self, interaction: Interaction) -> bool:
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        """
        Kick user without rejecting by default.
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
            await send_message(
                interaction,
                f"{target_user.display_name} is not in your channel.",
                ephemeral=True
            )
            return

        try:
            await target_user.move_to(None)  # Kick
            await send_message(
                interaction,
                f"{target_user.display_name} was kicked from your channel.",
                ephemeral=True
            )
        except Exception as e:
            await send_message(
                interaction,
                f"Failed to kick user: {e}",
                ephemeral=True
            )

    async def reject_button_callback(self, interaction: Interaction):
        """
        Kick + also reject from rejoining.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if not self.user_select.values:
            await send_message(interaction, "No user selected for reject.", ephemeral=True)
            return
        target_user = self.user_select.values[0]

        # Kick
        try:
            await target_user.move_to(None)
        except Exception as e:
            await send_message(
                interaction,
                f"Failed to kick user: {e}",
                ephemeral=True
            )
            return

        # Reject from reconnecting
        overwrites = channel.overwrites.copy()
        ow = overwrites.get(target_user, discord.PermissionOverwrite())
        ow.connect = False
        overwrites[target_user] = ow

        try:
            await edit_channel(channel, overwrites=overwrites)
            await send_message(
                interaction,
                f"{target_user.display_name} was kicked and rejected from rejoining.",
                ephemeral=True
            )
        except Exception as e:
            await send_message(
                interaction,
                f"Kicked but failed to reject rejoining: {e}",
                ephemeral=True
            )


# ---------------
# Priority Speaker
# ---------------
class PrioritySpeakerSelectView(View):
    """
    Asks the user to enable or disable priority speaker, then triggers target selection.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.select = Select(
            placeholder="Enable or Disable Priority Speaker",
            options=[
                SelectOption(label="Enable", value="enable"),
                SelectOption(label="Disable", value="disable"),
            ],
            min_values=1,
            max_values=1
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: Interaction):
        enable = (self.select.values[0] == "enable")
        view = PrioritySpeakerTargetView(self.bot, enable)
        # We only want to edit the ephemeral message from THIS interaction
        await edit_message(
            interaction,
            content="Select user(s) or role(s) for Priority Speaker:",
            view=view
        )

class PrioritySpeakerTargetView(View):
    """
    Allows selecting user or role for priority speaker.
    """
    def __init__(self, bot, enable):
        super().__init__(timeout=None)
        self.bot = bot
        self.enable = enable

        self.target_type_select = Select(
            placeholder="Select Target Type",
            options=[
                SelectOption(label="User", value="user"),
                SelectOption(label="Role", value="role")
            ],
            min_values=1,
            max_values=1
        )
        self.target_type_select.callback = self.target_type_callback
        self.add_item(self.target_type_select)

    async def target_type_callback(self, interaction: Interaction):
        selected = self.target_type_select.values[0]
        if selected == "user":
            view = PrioritySpeakerUserSelectView(self.bot, self.enable)
            await edit_message(
                interaction,
                content="Select user(s) for priority speaker:",
                view=view
            )
        else:  # "role"
            view = PrioritySpeakerRoleSelectView(self.bot, self.enable)
            await edit_message(
                interaction,
                content="Select role(s) for priority speaker:",
                view=view
            )

class PrioritySpeakerUserSelectView(View):
    def __init__(self, bot, enable):
        super().__init__(timeout=None)
        self.bot = bot
        self.enable = enable
        self.user_select = UserSelect(
            placeholder="Select user(s)",
            min_values=1,
            max_values=25
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def user_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        overwrites = channel.overwrites.copy()
        for user in self.user_select.values:
            ow = overwrites.get(user, discord.PermissionOverwrite())
            ow.priority_speaker = self.enable
            overwrites[user] = ow

            await set_priority_speaker_setting(
                interaction.user.id,
                user.id,
                "user",
                self.enable
            )

        try:
            await edit_channel(channel, overwrites=overwrites)
            status = "enabled" if self.enable else "disabled"
            # Provide ephemeral feedback
            await send_message(
                interaction,
                f"Priority speaker {status} for selected user(s).",
                ephemeral=True
            )
        except Exception as e:
            await send_message(interaction, f"Failed to update priority speaker: {e}", ephemeral=True)

class PrioritySpeakerRoleSelectView(View):
    def __init__(self, bot, enable):
        super().__init__(timeout=None)
        self.bot = bot
        self.enable = enable
        self.role_select = RoleSelect(
            placeholder="Select role(s)",
            min_values=1,
            max_values=25
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)

    async def role_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        overwrites = channel.overwrites.copy()
        for role in self.role_select.values:
            ow = overwrites.get(role, discord.PermissionOverwrite())
            ow.priority_speaker = self.enable
            overwrites[role] = ow

            await set_priority_speaker_setting(
                interaction.user.id,
                role.id,
                "role",
                self.enable
            )

        try:
            await edit_channel(channel, overwrites=overwrites)
            status = "enabled" if self.enable else "disabled"
            await send_message(
                interaction,
                f"Priority speaker {status} for selected role(s).",
                ephemeral=True
            )
        except Exception as e:
            await send_message(interaction, f"Failed to update priority speaker: {e}", ephemeral=True)


# ---------------
# Soundboard
# ---------------
class SoundboardSelectView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.select = Select(
            placeholder="Enable or Disable Soundboard",
            options=[
                SelectOption(label="Enable", value="enable"),
                SelectOption(label="Disable", value="disable")
            ],
            min_values=1,
            max_values=1
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: Interaction):
        enable = (self.select.values[0] == "enable")
        view = SoundboardTargetTypeView(self.bot, enable)
        await edit_message(
            interaction,
            content="Select target type for soundboard permission:",
            view=view
        )

class SoundboardTargetTypeView(View):
    def __init__(self, bot, enable):
        super().__init__(timeout=None)
        self.bot = bot
        self.enable = enable
        self.target_select = Select(
            placeholder="User, Role, or Everyone",
            options=[
                SelectOption(label="User", value="user"),
                SelectOption(label="Role", value="role"),
                SelectOption(label="Everyone", value="everyone")
            ],
            min_values=1,
            max_values=1
        )
        self.target_select.callback = self.target_select_callback
        self.add_item(self.target_select)

    async def target_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        selected = self.target_select.values[0]
        overwrites = channel.overwrites.copy()

        if selected == "everyone":
            default_role = channel.guild.default_role
            ow = overwrites.get(default_role, discord.PermissionOverwrite())
            ow.use_soundboard = self.enable
            overwrites[default_role] = ow

            await set_soundboard_setting(
                interaction.user.id,
                0,
                "everyone",
                self.enable
            )

            try:
                await edit_channel(channel, overwrites=overwrites)
                status = "enabled" if self.enable else "disabled"
                await send_message(
                    interaction,
                    f"Soundboard {status} for everyone.",
                    ephemeral=True
                )
            except Exception as e:
                await send_message(interaction, f"Failed to update soundboard: {e}", ephemeral=True)

        elif selected == "user":
            view = SoundboardUserSelectView(self.bot, self.enable)
            await edit_message(
                interaction,
                content="Select user(s) for soundboard setting:",
                view=view
            )
        else:  # "role"
            view = SoundboardRoleSelectView(self.bot, self.enable)
            await edit_message(
                interaction,
                content="Select role(s) for soundboard setting:",
                view=view
            )

class SoundboardUserSelectView(View):
    def __init__(self, bot, enable):
        super().__init__(timeout=None)
        self.bot = bot
        self.enable = enable
        self.user_select = UserSelect(
            placeholder="Select user(s)",
            min_values=1,
            max_values=25
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

    async def user_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        overwrites = channel.overwrites.copy()

        for user in self.user_select.values:
            ow = overwrites.get(user, discord.PermissionOverwrite())
            ow.use_soundboard = self.enable
            overwrites[user] = ow

            await set_soundboard_setting(
                interaction.user.id,
                user.id,
                "user",
                self.enable
            )

        try:
            await edit_channel(channel, overwrites=overwrites)
            status = "enabled" if self.enable else "disabled"
            await send_message(
                interaction,
                f"Soundboard {status} for selected user(s).",
                ephemeral=True
            )
        except Exception as e:
            await send_message(interaction, f"Failed to update soundboard: {e}", ephemeral=True)

class SoundboardRoleSelectView(View):
    def __init__(self, bot, enable):
        super().__init__(timeout=None)
        self.bot = bot
        self.enable = enable
        self.role_select = RoleSelect(
            placeholder="Select role(s)",
            min_values=1,
            max_values=25
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)

    async def role_select_callback(self, interaction: Interaction):
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        overwrites = channel.overwrites.copy()

        for role in self.role_select.values:
            ow = overwrites.get(role, discord.PermissionOverwrite())
            ow.use_soundboard = self.enable
            overwrites[role] = ow

            await set_soundboard_setting(
                interaction.user.id,
                role.id,
                "role",
                self.enable
            )

        try:
            await edit_channel(channel, overwrites=overwrites)
            status = "enabled" if self.enable else "disabled"
            await send_message(
                interaction,
                f"Soundboard {status} for selected role(s).",
                ephemeral=True
            )
        except Exception as e:
            await send_message(interaction, f"Failed to update soundboard: {e}", ephemeral=True)

class TargetTypeSelectView(View):
    """
    Select the type of target (user, role, or everyone for PTT).
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
        # Only for PTT, add 'Everyone'
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
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def target_type_callback(self, interaction: Interaction):
        selected_type = self.target_type_select.values[0]

        # If ptt + "everyone"
        if self.action == "ptt" and selected_type == "everyone":
            member = interaction.user
            channel = await get_user_channel(self.bot, member)
            if not channel:
                await send_message(interaction, "You don't own a channel.", ephemeral=True)
                return

            await set_ptt_setting(member.id, target_id=None, target_type="everyone", ptt_enabled=self.enable)
            permission_change = {
                "action": "ptt",
                "targets": [{"type": "everyone", "id": None}],
                "enable": self.enable
            }

            try:
                await apply_permissions_changes(channel, permission_change)
                status = "enabled" if self.enable else "disabled"
                await edit_message(
                    interaction,
                    content=f"PTT has been {status} for everyone in your channel.",
                    view=None
                )
            except Exception as e:
                await send_message(interaction, f"Failed to apply PTT settings: {e}", ephemeral=True)
            return

        # If 'user' or 'role'
        if selected_type == "user":
            view = SelectUserView(self.bot, self.action, enable=self.enable)
            await edit_message(
                interaction,
                content="Select users to apply the action:",
                view=view
            )
        elif selected_type == "role":
            view = SelectRoleView(self.bot, self.action, enable=self.enable)
            await edit_message(
                interaction,
                content="Select roles to apply the action:",
                view=view
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
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return False
        return True

    async def user_select_callback(self, interaction: Interaction):
        selected_users = self.user_select.values
        selected_user_ids = [u.id for u in selected_users]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if self.action == "ptt":
            permission_change = {
                "action": "ptt",
                "targets": [{"type": "user", "id": uid} for uid in selected_user_ids],
                "enable": self.enable
            }
        else:
            permission_change = {
                "action": self.action,
                "targets": [{"type": "user", "id": uid} for uid in selected_user_ids]
            }

        try:
            await apply_permissions_changes(channel, permission_change)
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await send_message(interaction, "", embed=embed, ephemeral=True)
            return

        # Update DB if needed
        if self.action in ["permit", "reject"]:
            for user_id in selected_user_ids:
                await set_channel_permission(interaction.user.id, user_id, "user", self.action)
        elif self.action == "ptt":
            for user_id in selected_user_ids:
                await set_ptt_setting(interaction.user.id, user_id, "user", self.enable)

        if self.action == "ptt":
            status = "PTT enabled" if self.enable else "PTT disabled"
        else:
            status = "permitted" if self.action == "permit" else "rejected"

        await send_message(
            interaction,
            f"Selected users have been {status} in your channel.",
            ephemeral=True
        )
        logger.info(
            f"{interaction.user.display_name} {status} users: {selected_user_ids} in channel '{channel.name}'."
        )

class SelectRoleView(View):
    """
    View to select multiple roles for certain actions (permit, reject, ptt).
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
        selected_role_ids = [r.id for r in selected_roles]
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if self.action == "ptt":
            permission_change = {
                "action": "ptt",
                "targets": [{"type": "role", "id": rid} for rid in selected_role_ids],
                "enable": self.enable
            }
        else:
            permission_change = {
                "action": self.action,
                "targets": [{"type": "role", "id": rid} for rid in selected_role_ids]
            }

        try:
            await apply_permissions_changes(channel, permission_change)
        except Exception as e:
            logger.exception(f"Failed to apply permissions: {e}")
            embed = create_error_embed("Failed to apply permissions. Please try again.")
            await send_message(interaction, "", embed=embed, ephemeral=True)
            return

        if self.action in ["permit", "reject"]:
            for role_id in selected_role_ids:
                await set_channel_permission(interaction.user.id, role_id, "role", self.action)
        elif self.action == "ptt":
            for role_id in selected_role_ids:
                await set_ptt_setting(interaction.user.id, role_id, "role", self.enable)

        if self.action == "ptt":
            status = "PTT settings updated"
        else:
            status = "permitted" if self.action == "permit" else "rejected"

        await send_message(
            interaction,
            f"Selected roles have been {status} in your channel.",
            ephemeral=True
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
                SelectOption(label="Enable PTT", value="enable", description="Force users/roles to use PTT"),
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
        await edit_message(
            interaction,
            content="Choose the type of target you want to apply the PTT setting to:",
            view=view
        )
