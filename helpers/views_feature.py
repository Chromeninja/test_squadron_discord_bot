"""
Feature Toggle Views

Interactive views for toggling voice channel features (PTT, Priority Speaker, Soundboard):
  - FeatureToggleView: enable/disable dropdown
  - FeatureTargetView: user / role / everyone target picker
  - FeatureUserSelectView: user multi-select for feature toggle
  - FeatureRoleSelectView: role filtered-select for feature toggle
"""

from __future__ import annotations

import contextlib

import discord  # type: ignore[import-not-found]
from discord import Interaction, SelectOption  # type: ignore[import-not-found]
from discord.ui import Select, UserSelect, View  # type: ignore[import-not-found]

from helpers.discord_api import send_message
from helpers.role_select_utils import load_selectable_roles, refresh_role_select
from helpers.views_voice import FilteredRoleSelect, _get_guild_and_jtc_for_user_channel
from helpers.voice_utils import (
    apply_voice_feature_toggle,
    get_user_channel,
    set_voice_feature_setting,
)
from utils.logging import get_logger

logger = get_logger(__name__)


class FeatureToggleView(View):
    """
    A unified view for toggling a feature (PTT, Priority Speaker, or Soundboard).

    Presents a select menu to choose between enabling or disabling the feature.
    The 'no_everyone' flag can be set to exclude the 'Everyone' option.
    """

    def __init__(self, bot, feature_name: str, no_everyone: bool = False) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
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
            max_values=1,
        )
        self.toggle_select.callback = self.toggle_select_callback
        self.add_item(self.toggle_select)

    async def toggle_select_callback(self, interaction: Interaction) -> None:
        """
        Callback for the toggle select.
        Determines if the feature should be enabled or disabled and shows the target selection view.
        """
        enable = self.toggle_select.values[0] == "enable"
        view = FeatureTargetView(self.bot, self.feature_name, enable, self.no_everyone)
        await send_message(
            interaction,
            f"Select who to {'enable' if enable else 'disable'} {self.feature_name} for:",
            ephemeral=True,
            view=view,
        )


class FeatureTargetView(View):
    """
    A view that lets the user choose a target type (User, Role, or Everyone) for the feature toggle.
    """

    def __init__(self, bot, feature_name: str, enable: bool, no_everyone: bool) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
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
            max_values=1,
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

    async def target_select_callback(self, interaction: Interaction) -> None:
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
            guild_id, jtc_channel_id = await _get_guild_and_jtc_for_user_channel(
                interaction.user, channel
            )
            await set_voice_feature_setting(
                self.feature_name,
                interaction.user.id,
                target_id,
                target_type,
                self.enable,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )
            await apply_voice_feature_toggle(
                channel, self.feature_name, target, self.enable
            )
            msg = (
                f"{self.feature_name.replace('_', ' ').title()} has been "
                f"{'enabled' if self.enable else 'disabled'} for everyone."
            )
            await send_message(interaction, msg, ephemeral=True)
        elif selection == "user":
            view = FeatureUserSelectView(self.bot, self.feature_name, self.enable)
            await send_message(
                interaction,
                f"Select user(s) to {'enable' if self.enable else 'disable'} "
                f"{self.feature_name} for:",
                ephemeral=True,
                view=view,
            )
        else:  # 'role'
            if self.feature_name in ["permit", "reject"]:
                from helpers.views_admin import TargetTypeSelectView
                view = TargetTypeSelectView(self.bot, action=self.feature_name)
            else:
                view = FeatureRoleSelectView(self.bot, self.feature_name, self.enable)
                # Load allowed roles from DB before sending view
                if interaction.guild:
                    await view.initialize(interaction.guild)
            await send_message(
                interaction,
                f"Select role(s) to {'enable' if self.enable else 'disable'} {self.feature_name} for:",
                ephemeral=True,
                view=view,
            )
        if interaction.message:
            with contextlib.suppress(discord.errors.NotFound):
                await interaction.message.edit(view=None)


class FeatureUserSelectView(View):
    """
    A view for selecting one or more users for a feature toggle (PTT, Priority Speaker, or Soundboard).
    """

    def __init__(self, bot, feature_name: str, enable: bool) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
        self.bot = bot
        self.feature_name = feature_name
        self.enable = enable

        self.user_select = UserSelect(
            placeholder="Select user(s)", min_values=1, max_values=25
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

    async def user_select_callback(self, interaction: Interaction) -> None:
        """
        Callback for when users are selected.
        Stores the feature setting for each selected user and applies it to the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        # Resolve guild/jtc context once for the user's channel
        guild_id, jtc_channel_id = await _get_guild_and_jtc_for_user_channel(
            interaction.user, channel
        )
        for user in self.user_select.values:
            await set_voice_feature_setting(
                self.feature_name,
                interaction.user.id,
                user.id,
                "user",
                self.enable,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )
            await apply_voice_feature_toggle(
                channel, self.feature_name, user, self.enable
            )

        msg = f"{self.feature_name.title()} {'enabled' if self.enable else 'disabled'} for selected user(s)."
        await send_message(interaction, msg, ephemeral=True)
        if interaction.message:
            with contextlib.suppress(discord.errors.NotFound):
                await interaction.message.edit(view=None)


class FeatureRoleSelectView(View):
    """
    A view for selecting one or more roles for a feature toggle (PTT, Priority Speaker, or Soundboard).
    """

    def __init__(self, bot, feature_name: str, enable: bool) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
        self.bot = bot
        self.feature_name = feature_name
        self.enable = enable

        # Allowed roles will be loaded from DB before view is sent
        # Start with empty list to show "No selectable roles available" placeholder
        self.role_select = FilteredRoleSelect(
            allowed_roles=[],  # Empty list triggers fallback option
            placeholder="Select role(s)",
            min_values=1,
            max_values=1,
            custom_id="feature_role_select_" + "z" * 10,
        )
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)
        # Initialize with placeholder option to satisfy Discord API requirements
        if self.bot.guilds:
            self.role_select.refresh_options(self.bot.guilds[0])

    async def initialize(self, guild: discord.Guild) -> None:
        """Load allowed roles from DB and refresh options before sending view."""
        allowed_roles = await load_selectable_roles(self.bot, guild)
        refresh_role_select(self.role_select, guild, allowed_roles)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Roles should already be loaded from initialize(), but refresh to be safe
        if interaction.guild:
            allowed_roles = await load_selectable_roles(self.bot, interaction.guild)
            refresh_role_select(self.role_select, interaction.guild, allowed_roles)
        return True

    async def role_select_callback(self, interaction: Interaction) -> None:
        """
        Callback for role selection.
        Instead of applying "permit/reject", it now properly enables/disables the selected feature.
        """
        try:
            # Get guild context early to pass to get_user_channel
            guild_id = interaction.guild.id if interaction.guild else None
            channel = await get_user_channel(
                self.bot, interaction.user, guild_id=guild_id
            )
            if not channel:
                await send_message(
                    interaction, "You don't own a channel.", ephemeral=True
                )
                return
            targets = []
            # resolve guild/jtc context once
            guild_id, jtc_channel_id = await _get_guild_and_jtc_for_user_channel(
                interaction.user, channel
            )
            for role_id_str in self.role_select.values:
                try:
                    role_id = int(role_id_str)
                except ValueError:
                    await send_message(
                        interaction, "No selectable roles available.", ephemeral=True
                    )
                    return
                targets.append({"type": "role", "id": role_id})
                # Store the feature setting in the database for future reference
                await set_voice_feature_setting(
                    feature=self.feature_name,
                    user_id=interaction.user.id,
                    target_id=role_id,
                    target_type="role",
                    enable=self.enable,
                    guild_id=guild_id,
                    jtc_channel_id=jtc_channel_id,
                )

            # Apply the actual permission change to the channel
            if interaction.guild:
                for target in targets:
                    if role := interaction.guild.get_role(target["id"]):
                        await apply_voice_feature_toggle(
                            channel, self.feature_name, role, self.enable
                        )

            msg = (
                f"{self.feature_name.replace('_', ' ').title()} has been "
                f"{'enabled' if self.enable else 'disabled'} for selected role(s)."
            )
            await send_message(interaction, msg, ephemeral=True)

            # Remove the selection UI after it's done
            if interaction.message:
                with contextlib.suppress(discord.errors.NotFound):
                    await interaction.message.edit(view=None)
        except Exception as e:
            logger.exception(
                f"Error in FeatureRoleSelectView callback: {e}",
                extra={"user_id": interaction.user.id},
            )
