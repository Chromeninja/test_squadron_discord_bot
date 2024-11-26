# cogs/voice.py

import discord
from discord.ext import commands
from discord import Interaction, app_commands
import asyncio
import json
import time

from config.config_loader import ConfigLoader
from helpers.logger import get_logger
from helpers.database import Database
from helpers.views import ChannelSettingsView, TargetTypeSelectView, PTTSelectView
from helpers.modals import CloseChannelConfirmationModal, ResetSettingsConfirmationModal, NameModal, LimitModal
from helpers.permissions_helper import apply_permissions_changes, reset_channel_permissions
from helpers.embeds import create_error_embed
from helpers.voice_utils import (
    get_user_channel,
    get_user_game_name,
    update_channel_settings,
    safe_create_voice_channel,
    safe_move_member,
    safe_delete_channel,
    safe_edit_channel
)

# Initialize logger
logger = get_logger(__name__)

class Voice(commands.GroupCog, name="voice"):
    """
    Cog for managing dynamic voice channels.
    """

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.bot_admin_role_ids = [int(role_id) for role_id in self.config['roles'].get('bot_admins', [])]
        self.cooldown_seconds = self.config['voice'].get('cooldown_seconds', 60)
        self.join_to_create_channel_ids = []
        self.voice_category_id = None
        self.managed_voice_channels = set()

    async def cog_load(self):
        """
        Called when the cog is loaded.
        """
        # Fetch settings from the database
        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", ('join_to_create_channel_ids',))
            row = await cursor.fetchone()
            if row:
                self.join_to_create_channel_ids = json.loads(row[0])
            else:
                logger.warning("Join to Create channel IDs not found in settings.")

            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", ('voice_category_id',))
            row = await cursor.fetchone()
            if row:
                self.voice_category_id = int(row[0])
            else:
                logger.warning("Voice category ID not found in settings.")

            # Load managed voice channels
            cursor = await db.execute("SELECT voice_channel_id FROM user_voice_channels")
            rows = await cursor.fetchall()
            self.managed_voice_channels = {row[0] for row in rows}

        if not self.join_to_create_channel_ids or not self.voice_category_id:
            logger.error("Voice setup is incomplete. Please run /voice setup command.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        Listener for voice state updates to create and delete dynamic voice channels.
        """
        logger.debug(f"Voice state update for {member.display_name}: before={before.channel}, after={after.channel}")

        # User left a voice channel
        if before.channel:
            # If the channel is a user-created channel (not a 'Join to Create' channel)
            if before.channel.id not in self.join_to_create_channel_ids:
                # Check if the channel is managed by the bot
                if before.channel.id in self.managed_voice_channels:
                    # Check if the channel is now empty
                    if len(before.channel.members) == 0:
                        try:
                            await before.channel.delete()
                            self.managed_voice_channels.remove(before.channel.id)
                            async with Database.get_connection() as db:
                                await db.execute("DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (before.channel.id,))
                                await db.commit()
                            logger.info(f"Deleted empty voice channel '{before.channel.name}'")
                        except Exception as e:
                            logger.exception(f"Error deleting empty voice channel '{before.channel.name}': {e}")
                else:
                    logger.debug(f"Channel '{before.channel.name}' (ID: {before.channel.id}) is not managed by the bot. Skipping deletion.")
            # Continue to check if the user moved into a "Join to Create" channel
            # This ensures that moving out doesn't interfere with the creation logic

        # User joined a "Join to Create" voice channel
        if after.channel and after.channel.id in self.join_to_create_channel_ids:
            if not self.voice_category_id:
                logger.error("Voice setup is incomplete. Please run /voice setup command.")
                return

            # Check if the user is already in a managed voice channel to prevent loops
            if member.voice and member.voice.channel and member.voice.channel.id in self.managed_voice_channels:
                logger.debug(f"User '{member.display_name}' is already in a managed channel. Skipping creation.")
                return

            # Check for cooldown
            current_time = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute("SELECT last_created FROM voice_cooldowns WHERE user_id = ?", (member.id,))
                cooldown_row = await cursor.fetchone()
                if cooldown_row:
                    last_created = cooldown_row[0]
                    elapsed_time = current_time - last_created
                    if elapsed_time < self.cooldown_seconds:
                        remaining_time = self.cooldown_seconds - elapsed_time
                        try:
                            await member.send(f"You're creating channels too quickly. Please wait {remaining_time} seconds.")
                        except discord.Forbidden:
                            logger.warning(f"Cannot send DM to {member.display_name}.")
                        return

            # Create voice channel
            try:
                guild = member.guild
                category = guild.get_channel(self.voice_category_id)
                if not category:
                    logger.error("Voice category not found.")
                    return

                # Retrieve saved settings or set defaults
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT channel_name, user_limit, permissions FROM channel_settings WHERE user_id = ?",
                        (member.id,),
                    )
                    settings_row = await cursor.fetchone()

                # Determine channel name
                if settings_row and settings_row[0]:
                    channel_name = settings_row[0]
                else:
                    channel_name = get_user_game_name(member) or f"{member.display_name}'s Channel"
                channel_name = channel_name[:32]  # Ensure name is within 32 characters

                # Determine user limit
                user_limit = settings_row[1] if settings_row and settings_row[1] else None

                # Define permission overwrites
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=False),
                    member: discord.PermissionOverwrite(manage_channels=True, connect=True)
                }

                # Create the channel with the settings
                new_channel = await safe_create_voice_channel(
                    guild=guild,
                    name=channel_name,
                    category=category,
                    user_limit=user_limit,
                    overwrites=overwrites
                )

                # Apply saved permissions (like PTT settings)
                if settings_row and settings_row[2]:
                    permissions = json.loads(settings_row[2])
                    if not isinstance(permissions, dict):
                        permissions = {}
                    await apply_permissions_changes(new_channel, permissions)
                else:
                    permissions = {}

                # Move the member to the new channel
                await safe_move_member(member, new_channel)

                # Store channel in the database and in-memory set
                async with Database.get_connection() as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO user_voice_channels (voice_channel_id, user_id) VALUES (?, ?)",
                        (new_channel.id, member.id)
                    )
                    await db.execute(
                        "INSERT OR REPLACE INTO voice_cooldowns (user_id, last_created) VALUES (?, ?)",
                        (member.id, current_time)
                    )
                    await db.commit()
                    self.managed_voice_channels.add(new_channel.id)
                    logger.info(f"Created voice channel '{new_channel.name}' for {member.display_name}")

                # Send settings view to the channel
                try:
                    view = ChannelSettingsView(self.bot, member)
                    await new_channel.send(f"{member.mention}, configure your channel settings:", view=view)
                except discord.Forbidden:
                    logger.warning(f"Cannot send message to channel '{new_channel.name}' (ID: {new_channel.id}).")
                except Exception as e:
                    logger.exception(f"Error sending settings view to channel '{new_channel.name}' (ID: {new_channel.id}): {e}")

                # Wait until the channel is empty
                await self._wait_for_channel_empty(new_channel)
                # Deletion logic removed to prevent double deletion
            except Exception as e:
                logger.exception(f"Error creating voice channel for {member.display_name}: {e}")

    async def _wait_for_channel_empty(self, channel: discord.VoiceChannel):
        """
        Waits until the voice channel is empty before proceeding.

        Args:
            channel (discord.VoiceChannel): The channel to monitor.
        """
        while True:
            await asyncio.sleep(5)
            if len(channel.members) == 0:
                break

    async def _apply_channel_permissions(self, channel: discord.VoiceChannel, permissions: dict):
        """
        Applies saved permissions to the channel.

        Args:
            channel (discord.VoiceChannel): The channel to modify.
            permissions (dict): The permissions to apply.
        """
        if not isinstance(permissions, dict):
            permissions = {}
        guild = channel.guild
        # Apply PTT settings
        ptt_settings = permissions.get('ptt', [])
        for ptt_setting in ptt_settings:
            await apply_permissions_changes(channel, ptt_setting)

        # Apply other permissions (permit/reject)
        perm_settings = permissions.get('permissions', [])
        for perm_change in perm_settings:
            await apply_permissions_changes(channel, perm_change)

    @app_commands.command(name="setup", description="Set up the voice channel system")
    @app_commands.guild_only()
    @app_commands.describe(category="The category to place voice channels in", num_channels="Number of 'Join to Create' channels")
    async def setup_voice(self, interaction: discord.Interaction, category: discord.CategoryChannel, num_channels: int):
        """
        Sets up the voice channel system in the guild.
        """
        member = interaction.user
        if not any(role.id in self.bot_admin_role_ids for role in member.roles):
            await interaction.response.send_message("Only bot admins can set up the bot.", ephemeral=True)
            return

        if num_channels < 1 or num_channels > 10:
            await interaction.response.send_message("Please specify a number of channels between 1 and 10.", ephemeral=True)
            return

        await interaction.response.send_message("Starting setup...", ephemeral=True)

        # Save the category ID
        async with Database.get_connection() as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ('voice_category_id', str(category.id))
            )
            await db.commit()
        self.voice_category_id = category.id

        # Create 'Join to Create' channels
        self.join_to_create_channel_ids = []
        try:
            for i in range(num_channels):
                channel_name = f"Join to Create #{i+1}" if num_channels > 1 else "Join to Create"
                voice_channel = await safe_create_voice_channel(
                    guild=interaction.guild,
                    name=channel_name,
                    category=category
                )
                self.join_to_create_channel_ids.append(voice_channel.id)

            # Save the channel IDs
            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ('join_to_create_channel_ids', json.dumps(self.join_to_create_channel_ids))
                )
                await db.commit()

            await interaction.followup.send("Setup complete!", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error creating voice channels: {e}")
            await interaction.followup.send("Failed to create voice channels. Please ensure the bot has the necessary permissions.", ephemeral=True)

    @app_commands.command(name="permit", description="Permit users/roles to join your channel")
    @app_commands.guild_only()
    async def permit_user_voice(self, interaction: discord.Interaction):
        """
        Allows users to permit other users or roles to join their voice channel.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Send the TargetTypeSelectView
        view = TargetTypeSelectView(self.bot, member, action="permit")
        await interaction.response.send_message("Choose the type of target you want to permit:", view=view, ephemeral=True)

    @app_commands.command(name="reject", description="Reject users/roles from joining your channel")
    @app_commands.guild_only()
    async def reject_user_voice(self, interaction: discord.Interaction):
        """
        Rejects users or roles from joining the user's voice channel.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Send the TargetTypeSelectView
        view = TargetTypeSelectView(self.bot, member, action="reject")
        await interaction.response.send_message("Choose the type of target you want to reject:", view=view, ephemeral=True)

    @app_commands.command(name="ptt", description="Manage PTT settings in your voice channel")
    @app_commands.guild_only()
    async def ptt(self, interaction: discord.Interaction):
        """
        Manages PTT (push-to-talk) settings for users or roles in the user's voice channel.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Send a view to select enable or disable PTT
        view = PTTSelectView(self.bot, member)
        await interaction.response.send_message("Do you want to enable or disable PTT?", view=view, ephemeral=True)

    @app_commands.command(name="lock", description="Lock your voice channel")
    @app_commands.guild_only()
    async def lock_voice(self, interaction: discord.Interaction):
        """
        Locks the user's voice channel.
        """
        await self._change_channel_lock(interaction, lock=True)

    @app_commands.command(name="unlock", description="Unlock your voice channel")
    @app_commands.guild_only()
    async def unlock_voice(self, interaction: discord.Interaction):
        """
        Unlocks the user's voice channel.
        """
        await self._change_channel_lock(interaction, lock=False)

    async def _change_channel_lock(self, interaction: discord.Interaction, lock: bool):
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Define permission overwrites
        overwrites = channel.overwrites.copy()
        default_role = interaction.guild.default_role

        overwrite = overwrites.get(default_role, discord.PermissionOverwrite())
        overwrite.connect = not lock
        overwrites[default_role] = overwrite

        # Apply the permission changes with rate limiting
        try:
            await safe_edit_channel(channel, overwrites=overwrites)
        except Exception as e:
            await interaction.response.send_message("Failed to update channel permissions.", ephemeral=True)
            return

        # Update settings using the helper function
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT permissions FROM channel_settings WHERE user_id = ?",
                (member.id,)
            )
            settings_row = await cursor.fetchone()
            if settings_row and settings_row[0]:
                permissions = json.loads(settings_row[0])
                if not isinstance(permissions, dict):
                    permissions = {}
            else:
                permissions = {}

            permissions['lock'] = lock

            await update_channel_settings(member.id, permissions=permissions)

        status = "locked" if lock else "unlocked"
        await interaction.response.send_message(f"Your voice channel has been {status}.", ephemeral=True)
        logger.info(f"{member.display_name} {status} their voice channel.")

    @app_commands.command(name="name", description="Change your voice channel's name")
    @app_commands.guild_only()
    async def rename_voice(self, interaction: discord.Interaction):
        """
        Changes the user's voice channel name.
        """
        member = interaction.user
        await interaction.response.send_modal(NameModal(self.bot, member))

    @app_commands.command(name="limit", description="Set user limit for your voice channel")
    @app_commands.guild_only()
    async def set_limit_voice(self, interaction: discord.Interaction):
        """
        Sets the user limit for the user's voice channel.
        """
        member = interaction.user
        await interaction.response.send_modal(LimitModal(self.bot, member))

    @app_commands.command(name="close", description="Close your voice channel")
    @app_commands.guild_only()
    async def close_channel(self, interaction: discord.Interaction):
        """
        Closes the user's voice channel.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        await interaction.response.send_modal(CloseChannelConfirmationModal(self.bot, member, channel))

    @app_commands.command(name="reset", description="Reset your channel settings to default")
    @app_commands.guild_only()
    async def reset_channel_settings(self, interaction: discord.Interaction):
        """
        Resets the user's channel settings to default.
        """
        member = interaction.user
        await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot, member))

    @app_commands.command(name="help", description="Show help for voice commands")
    @app_commands.guild_only()
    async def voice_help(self, interaction: discord.Interaction):
        """
        Displays help information for voice commands.
        """
        help_text = (
            "**Voice Commands:**\n"
            "/voice setup - Set up the voice channel system (Bot Admins only)\n"
            "/voice lock - Lock your voice channel\n"
            "/voice unlock - Unlock your voice channel\n"
            "/voice name - Change your voice channel's name\n"
            "/voice limit - Set user limit for your voice channel\n"
            "/voice permit - Permit users/roles to join your channel\n"
            "/voice reject - Reject users/roles from joining your channel\n"
            "/voice ptt - Manage PTT settings in your channel\n"
            "/voice close - Close your voice channel\n"
            "/voice reset - Reset your channel settings to default\n"
            "/voice help - Show this help message"
        )
        await interaction.response.send_message(help_text, ephemeral=True)

    async def _reset_current_channel_settings(self, member):
        """
        Resets the settings of the user's current voice channel to default.

        Args:
            member (discord.Member): The member whose channel settings are to be reset.
        """
        channel = await get_user_channel(self.bot, member)
        if not channel:
            return

        # Define desired changes
        changes = {}
        default_name = f"{member.display_name}'s Channel"[:32]
        if channel.name != default_name:
            changes['name'] = default_name

        # Reset overwrites to default
        overwrites = {
            member: discord.PermissionOverwrite(manage_channels=True, connect=True),
            channel.guild.default_role: discord.PermissionOverwrite(connect=True)
        }
        changes['overwrites'] = overwrites

        # Reset user limit if it's not already None
        if channel.user_limit is not None:
            changes['user_limit'] = None

        # Apply all changes with rate limiting
        try:
            if changes:
                await safe_edit_channel(channel, **changes)
                logger.info(f"Reset channel settings for '{member.display_name}'")
        except Exception as e:
            logger.exception(f"Failed to reset channel settings for {member.display_name}: {e}")
            return

        # Remove settings from the database
        await update_channel_settings(member.id, channel_name=None, user_limit=None, permissions=None)

        logger.info(f"Reset settings for {member.display_name}'s channel.")

async def setup(bot):
    await bot.add_cog(Voice(bot))
    logger.info("Voice cog loaded.")
