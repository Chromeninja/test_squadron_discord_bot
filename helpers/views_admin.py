"""
Admin / Permit-Reject Views

Interactive views for permit/reject actions on voice channel access:
  - TargetTypeSelectView: user vs role picker for permit/reject
  - SelectUserView: multi-user select for permit/reject
  - SelectRoleView: filtered role select for permit/reject
"""

from __future__ import annotations

import contextlib

import discord  # type: ignore[import-not-found]
from discord import Interaction, SelectOption  # type: ignore[import-not-found]
from discord.ui import Select, UserSelect, View  # type: ignore[import-not-found]

from helpers.discord_api import send_message
from helpers.permissions_helper import (
    apply_permissions_changes,
    store_permit_reject_in_db,
)
from helpers.role_select_utils import load_selectable_roles, refresh_role_select
from helpers.views_voice import FilteredRoleSelect, _get_guild_and_jtc_for_user_channel
from helpers.voice_utils import get_user_channel
from utils.logging import get_logger

logger = get_logger(__name__)


class TargetTypeSelectView(View):
    """
    View to select the target type for permit/reject actions.

    Only offers 'User' and 'Role' options.
    """

    def __init__(self, bot, action: str) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
        self.bot = bot
        self.action = action

        options = [
            SelectOption(
                label="User", value="user", description="Select specific user(s)"
            ),
            SelectOption(label="Role", value="role", description="Select a role"),
        ]
        self.select = Select(
            placeholder="Select Target Type",
            min_values=1,
            max_values=1,
            options=options,
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

    async def select_callback(self, interaction: Interaction) -> None:
        """
        Callback for target type selection.
        Depending on the selection, shows either a user or role selection view.
        """
        choice = self.select.values[0]
        if choice == "user":
            view = SelectUserView(self.bot, action=self.action)
            await send_message(
                interaction,
                f"Select user(s) to {self.action}:",
                ephemeral=True,
                view=view,
            )
        else:
            view = SelectRoleView(self.bot, action=self.action)
            # Load allowed roles from DB before sending view
            if interaction.guild:
                await view.initialize(interaction.guild)
            await send_message(
                interaction,
                f"Select role(s) to {self.action}:",
                ephemeral=True,
                view=view,
            )
        if interaction.message:
            with contextlib.suppress(discord.errors.NotFound):
                await interaction.message.edit(view=None)


class SelectUserView(View):
    """
    View for selecting multiple users to apply permit/reject actions.
    """

    def __init__(self, bot, action: str) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
        self.bot = bot
        self.action = action
        self.user_select = UserSelect(
            placeholder="Select user(s)", min_values=1, max_values=25
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

    async def user_select_callback(self, interaction: Interaction) -> None:
        """
        Callback for when users are selected.
        Stores the permit/reject settings in the database and applies the changes to the channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        targets = []
        # Resolve guild/jtc context for this user's channel
        guild_id, jtc_channel_id = await _get_guild_and_jtc_for_user_channel(
            interaction.user, channel
        )
        for user in self.user_select.values:
            targets.append({"type": "user", "id": user.id})
            await store_permit_reject_in_db(
                interaction.user.id,
                user.id,
                "user",
                self.action,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )
        permission_change = {"action": self.action, "targets": targets}
        await apply_permissions_changes(channel, permission_change)
        await send_message(
            interaction,
            f"Selected user(s) have been {self.action}ed.",
            ephemeral=True,
        )
        if interaction.message:
            with contextlib.suppress(discord.errors.NotFound):
                await interaction.message.edit(view=None)


class SelectRoleView(View):
    """
    View for selecting multiple roles to apply permit/reject actions.
    """

    def __init__(self, bot, action: str) -> None:
        # Temporary helper view -> finite timeout
        super().__init__(timeout=180)
        self.bot = bot
        self.action = action

        # Allowed roles will be loaded from DB before view is sent
        # Start with empty list to show "No selectable roles available" placeholder
        self.role_select = FilteredRoleSelect(
            allowed_roles=[],  # Empty list triggers fallback option
            placeholder="Select role(s)",
            min_values=1,
            max_values=1,
            custom_id="permit_role_select_" + "z" * 10,
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
        # Load allowed roles from config service on first interaction
        if interaction.guild:
            allowed_roles = await load_selectable_roles(self.bot, interaction.guild)
            refresh_role_select(self.role_select, interaction.guild, allowed_roles)

        if not interaction.guild:
            return False
        return True

    async def role_select_callback(self, interaction: Interaction) -> None:
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        targets = []
        # Resolve guild/jtc context for this user's channel
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
            await store_permit_reject_in_db(
                interaction.user.id,
                role_id,
                "role",
                self.action,
                guild_id=guild_id,
                jtc_channel_id=jtc_channel_id,
            )

        permission_change = {"action": self.action, "targets": targets}
        await apply_permissions_changes(channel, permission_change)
        await send_message(
            interaction,
            f"Selected role(s) have been {self.action}ed.",
            ephemeral=True,
        )
        if interaction.message:
            with contextlib.suppress(discord.errors.NotFound):
                await interaction.message.edit(view=None)
