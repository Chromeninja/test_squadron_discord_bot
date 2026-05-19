"""
Voice Channel Views

Interactive views and helpers for voice channel management:
  - FilteredRoleSelect: role dropdown filtered to allowed IDs
  - ChannelSettingsView: persistent settings + permissions dropdowns
  - KickUserSelectView: select a member to kick from the owner's channel
"""

from __future__ import annotations

import contextlib

import discord  # type: ignore[import-not-found]
from discord import Interaction, SelectOption  # type: ignore[import-not-found]
from discord.ui import (  # type: ignore[import-not-found]
    Button,
    Select,
    UserSelect,
    View,
)

from helpers.discord_api import edit_channel, send_message
from helpers.modals import (
    LimitModal,
    NameModal,
    ResetSettingsConfirmationModal,
)
from helpers.permissions_helper import apply_permissions_changes
from helpers.voice_settings import fetch_channel_settings
from helpers.voice_utils import (
    create_voice_settings_embed,
    format_channel_settings,
    get_user_channel,
    get_user_game_name,
    update_channel_settings,
)
from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)


async def _get_guild_and_jtc_for_user_channel(
    user: discord.abc.User, channel: discord.abc.GuildChannel
) -> tuple[int | None, int | None]:
    """
    Helper: return (guild_id, jtc_channel_id) for a user's owned voice channel mapping.
    Returns (guild_id, jtc_channel_id) where jtc_channel_id may be None if not stored.
    """
    guild_id = channel.guild.id if channel and channel.guild else None
    jtc_channel_id = None
    if guild_id is not None:
        jtc_channel_id = await BaseRepository.fetch_value(
            "SELECT jtc_channel_id FROM voice_channels WHERE owner_id = ? AND guild_id = ? AND voice_channel_id = ? AND is_active = 1",
            (user.id, guild_id, channel.id),
        )
    return guild_id, jtc_channel_id


# Custom select for roles with optional filtering based on allowed role IDs.
# If allowed_roles is provided (a list of role IDs), only roles in that list will be displayed.
# Otherwise, all roles in the guild will be shown.
class FilteredRoleSelect(Select):
    def __init__(
        self,
        *,
        allowed_roles: list | None = None,
        placeholder: str = "Select role(s)",
        min_values: int = 1,
        max_values: int = 25,
        custom_id: str | None = None,
        **kwargs,
    ):
        base = "filtered_role_select_"
        if custom_id is None or len(custom_id) < len(base):
            extra = "x" * (25 - len(base))
            custom_id = base + extra
        super().__init__(
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=[],
            custom_id=custom_id,
            **kwargs,
        )
        self.allowed_roles = allowed_roles

    def refresh_options(self, guild: discord.Guild) -> None:
        logger.debug(
            f"FilteredRoleSelect.refresh_options: guild={guild.id}, allowed_roles={self.allowed_roles}"
        )
        logger.debug(
            f"FilteredRoleSelect.refresh_options: guild has {len(guild.roles)} roles: {[f'{r.name}({r.id})' for r in guild.roles[:5]]}"
        )
        if self.allowed_roles is None:
            filtered_options = [
                SelectOption(label=role.name, value=str(role.id))
                for role in guild.roles
            ]
        else:
            filtered_options = [
                SelectOption(label=role.name, value=str(role.id))
                for role in guild.roles
                if role.id in self.allowed_roles
            ]
            logger.debug(
                f"FilteredRoleSelect.refresh_options: filtered {len(filtered_options)} roles from allowed list"
            )
        if not filtered_options:
            logger.warning(
                "FilteredRoleSelect: No matching roles found; adding fallback option."
            )
            filtered_options = [
                SelectOption(
                    label="No selectable roles available",
                    value="no_selectable_roles_available",
                )
            ]
            self.disabled = True
        else:
            self.disabled = False
        self.options = filtered_options
        logger.debug(
            f"FilteredRoleSelect options refreshed: {[opt.label for opt in self.options]}"
        )


class ChannelSettingsView(View):
    """
    Main view for channel settings.

    Contains two dropdown menus:
      - Channel Settings: Options include Name, Limit, Game, List, and Reset.
      - Channel Permissions: Options include Lock, Unlock, Permit, Reject, PTT, Kick, Priority Speaker, and Soundboard.
    """

    def __init__(self, bot) -> None:
        # This view is persistent across restarts (timeout=None) and must have stable custom_ids
        super().__init__(timeout=None)
        self.bot = bot
        # Add a stable custom_id so the bot can restore this persistent view after a restart
        self.channel_settings_select = Select(
            placeholder="Channel Settings",
            min_values=1,
            max_values=1,
            custom_id="channel_settings_select_main",
            options=[
                SelectOption(
                    label="Name",
                    value="name",
                    description="Change the name of the channel",
                    emoji="✏️",
                ),
                SelectOption(
                    label="Limit",
                    value="limit",
                    description="Limit how many users can join",
                    emoji="🔢",
                ),
                SelectOption(
                    label="Game",
                    value="game",
                    description="Set channel name to your current game",
                    emoji="🎮",
                ),
                SelectOption(
                    label="List",
                    value="list",
                    description="View current channel settings and permissions",
                    emoji="📜",
                ),
                SelectOption(
                    label="Reset",
                    value="reset",
                    description="Reset your channel settings to default",
                    emoji="🔄",
                ),
            ],
        )
        self.channel_settings_select.callback = self.channel_settings_callback
        self.add_item(self.channel_settings_select)

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
                    emoji="🔒",
                ),
                SelectOption(
                    label="Unlock",
                    value="unlock",
                    description="Unlock the channel",
                    emoji="🔓",
                ),
                SelectOption(
                    label="Permit",
                    value="permit",
                    description="Permit users/roles to join",
                    emoji="✅",
                ),
                SelectOption(
                    label="Reject",
                    value="reject",
                    description="Reject users/roles from joining",
                    emoji="🚫",
                ),
                SelectOption(
                    label="PTT",
                    value="ptt",
                    description="Manage PTT settings",
                    emoji="🎙️",
                ),
            ],
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
                    label="Kick",
                    value="kick",
                    description="Kick a user from your channel",
                    emoji="👢",
                ),
                SelectOption(
                    label="Priority Speaker",
                    value="priority_speaker",
                    description="Grant/revoke priority speaker",
                    emoji="📢",
                ),
                SelectOption(
                    label="Soundboard",
                    value="soundboard",
                    description="Enable/disable soundboard",
                    emoji="🔊",
                ),
            ],
        )
        self.channel_permissions_select_2.callback = self.channel_permissions_callback
        self.add_item(self.channel_permissions_select_2)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensure that the interacting user owns a voice channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(
                interaction,
                "You cannot interact with this. You don't own a channel.",
                ephemeral=True,
            )
            return False
        return True

    async def channel_settings_callback(self, interaction: Interaction) -> None:
        """
        Handle selections from the channel settings dropdown.

        Depending on the selection, open the appropriate modal or display current settings.
        """
        if not interaction.guild:
            await send_message(
                interaction, "This command must be used in a server.", ephemeral=True
            )
            return
        guild_id = interaction.guild.id
        channel = await get_user_channel(self.bot, interaction.user, guild_id)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        # Get the JTC channel ID from the database
        jtc_channel_id = await BaseRepository.fetch_value(
            "SELECT jtc_channel_id FROM voice_channels WHERE owner_id = ? AND guild_id = ? AND voice_channel_id = ? AND is_active = 1",
            (interaction.user.id, guild_id, channel.id),
        )

        selected = self.channel_settings_select.values[0]

        try:
            if selected == "name":
                modal = NameModal(self.bot, guild_id, jtc_channel_id)
                await interaction.response.send_modal(modal)
            elif selected == "limit":
                modal = LimitModal(self.bot, guild_id, jtc_channel_id)
                await interaction.response.send_modal(modal)
            elif selected == "game":
                if not interaction.guild:
                    await send_message(
                        interaction,
                        "This command must be used in a server.",
                        ephemeral=True,
                    )
                    return
                member = interaction.guild.get_member(interaction.user.id)
                if not member:
                    await send_message(
                        interaction,
                        "Unable to retrieve your member data.",
                        ephemeral=True,
                    )
                    return
                game_name = get_user_game_name(member)
                if not game_name:
                    await send_message(
                        interaction,
                        "You are not currently playing a game.",
                        ephemeral=True,
                    )
                    return

                await edit_channel(channel, name=game_name[:32])
                await update_channel_settings(
                    interaction.user.id,
                    guild_id,
                    jtc_channel_id,
                    channel_name=game_name,
                )
                e = discord.Embed(
                    description=f"Channel name set to your current game: **{game_name}**.",
                    color=discord.Color.green(),
                )
                await send_message(interaction, "", embed=e, ephemeral=True)
            elif selected == "list":
                # Provide guild/jtc context when available so DB lookups are scoped
                guild_id = interaction.guild.id if interaction.guild else None
                # attempt to resolve jtc for this user's active channel
                channel = await get_user_channel(self.bot, interaction.user, guild_id)
                jtc_channel_id = None
                if channel:
                    _, jtc_channel_id = await _get_guild_and_jtc_for_user_channel(
                        interaction.user, channel
                    )
                result = await fetch_channel_settings(
                    self.bot,
                    interaction,
                )
                if not result or not result.get("settings"):
                    await interaction.response.send_message(
                        "❌ No channel settings found. Create or join a voice channel first!",
                        ephemeral=True,
                    )
                    return

                settings = result["settings"]
                formatted = format_channel_settings(settings, interaction)
                embed = create_voice_settings_embed(
                    settings=settings,
                    formatted=formatted,
                    title="Channel Settings & Permissions",
                    footer="Use /voice commands or the dropdown menu to adjust these settings.",
                )
                await send_message(interaction, "", embed=embed, ephemeral=True)
            elif selected == "reset":
                await interaction.response.send_modal(
                    ResetSettingsConfirmationModal(self.bot)
                )
            else:
                await send_message(
                    interaction, "Unknown option selected.", ephemeral=True
                )

                # Update the original message to preserve the view.
            if interaction.message:
                await interaction.message.edit(view=self)
        except Exception as e:
            logger.exception("Error in channel_settings_callback", exc_info=e)
            await send_message(interaction, "An error occurred.", ephemeral=True)

    async def channel_permissions_callback(self, interaction: Interaction) -> None:
        """
        Handle selections from the channel permissions dropdown.

        Depending on the selection, either display an additional view or apply permission changes immediately.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        selected = None
        try:
            if isinstance(interaction.data, dict):
                values = interaction.data.get("values") or []
                if values:
                    selected = values[0]
            if selected is None:
                # Fallback for some discord.py versions
                comp = getattr(interaction, "component", None)
                if comp:
                    selected = (getattr(comp, "values", []) or [None])[0]
            if selected is None:
                await send_message(interaction, "No option selected.", ephemeral=True)
                return
        except Exception as e:
            logger.exception("Error reading select value", exc_info=e)
            await send_message(interaction, "An error occurred.", ephemeral=True)
            return

        if selected in ["permit", "reject"]:
            from helpers.views_admin import TargetTypeSelectView
            view = TargetTypeSelectView(self.bot, action=selected)
            await send_message(
                interaction,
                f"Choose the type of target you want to {selected}:",
                view=view,
                ephemeral=True,
            )
        elif selected in ["lock", "unlock"]:
            lock = selected == "lock"
            permission_change = {
                "action": selected,
                "targets": [{"type": "role", "id": channel.guild.default_role.id}],
            }
            await apply_permissions_changes(channel, permission_change)
            # Store lock state scoped to this guild/JTC if possible
            guild_id, jtc_channel_id = await _get_guild_and_jtc_for_user_channel(
                interaction.user, channel
            )
            await update_channel_settings(
                interaction.user.id, guild_id, jtc_channel_id, lock=1 if lock else 0
            )
            status = "locked" if lock else "unlocked"
            await send_message(
                interaction, f"Your voice channel has been {status}.", ephemeral=True
            )
        elif selected == "ptt":
            from helpers.views_feature import FeatureToggleView
            view = FeatureToggleView(self.bot, feature_name="ptt")
            await send_message(
                interaction,
                "Do you want to enable or disable PTT?",
                view=view,
                ephemeral=True,
            )
        elif selected == "kick":
            view = KickUserSelectView(self.bot)
            await send_message(
                interaction, "Select a user to kick:", view=view, ephemeral=True
            )
        elif selected == "priority_speaker":
            from helpers.views_feature import FeatureToggleView
            view = FeatureToggleView(
                self.bot, feature_name="priority_speaker", no_everyone=True
            )
            await send_message(
                interaction,
                "Enable or disable Priority Speaker?",
                view=view,
                ephemeral=True,
            )
        elif selected == "soundboard":
            from helpers.views_feature import FeatureToggleView
            view = FeatureToggleView(self.bot, feature_name="soundboard")
            await send_message(
                interaction, "Enable or disable Soundboard?", view=view, ephemeral=True
            )
        else:
            await send_message(interaction, "Unknown option.", ephemeral=True)

        if interaction.message:
            with contextlib.suppress(discord.errors.NotFound):
                await interaction.message.edit(view=self)


class KickUserSelectView(View):
    """
    View that allows the channel owner to select a user to kick,
    with an optional button to also reject them from rejoining.
    """

    def __init__(self, bot) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
        self.bot = bot

        self.user_select = UserSelect(
            placeholder="Select user to kick", min_values=1, max_values=1
        )
        self.user_select.callback = self.user_select_callback
        self.add_item(self.user_select)

        self.reject_button = Button(
            label="Also Reject from Rejoining", style=discord.ButtonStyle.danger
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

    async def user_select_callback(self, interaction: Interaction) -> None:
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
            await send_message(
                interaction,
                f"{target_user.display_name} is not in your channel.",
                ephemeral=True,
            )
            return

        if not isinstance(target_user, discord.Member):
            await send_message(interaction, "Cannot kick this user.", ephemeral=True)
            return

        try:
            await target_user.move_to(None)
            await send_message(
                interaction,
                f"{target_user.display_name} was kicked from your channel.",
                ephemeral=True,
            )
        except Exception as e:
            await send_message(interaction, f"Failed to kick user: {e}", ephemeral=True)

    async def reject_button_callback(self, interaction: Interaction) -> None:
        """
        Callback for rejecting a user after kicking them.
        Updates the channel's permission overwrites to prevent the user from rejoining.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if not self.user_select.values:
            await send_message(
                interaction, "No user selected for reject.", ephemeral=True
            )
            return

        target_user = self.user_select.values[0]
        if not isinstance(target_user, discord.Member):
            await send_message(interaction, "Cannot kick this user.", ephemeral=True)
            return
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
            await send_message(
                interaction,
                f"{target_user.display_name} was kicked and rejected from rejoining.",
                ephemeral=True,
            )
        except Exception as e:
            await send_message(
                interaction,
                f"Kicked but failed to reject rejoining: {e}",
                ephemeral=True,
            )
