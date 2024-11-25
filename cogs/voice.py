# cogs/voice.py

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import time

from config.config_loader import ConfigLoader
from helpers.logger import get_logger
from helpers.database import Database
from helpers.views import ChannelSettingsView, TargetTypeSelectView
from helpers.modals import CloseChannelConfirmationModal, ResetSettingsConfirmationModal, NameModal, LimitModal
from helpers.permissions_helper import apply_ptt_settings, apply_permissions_changes, reset_channel_permissions
from helpers.embeds import create_error_embed

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

        if not self.join_to_create_channel_ids or not self.voice_category_id:
            logger.error("Voice setup is incomplete. Please run /voice setup command.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        Listener for voice state updates to create and delete dynamic voice channels.
        """
        # User left a voice channel
        if before.channel and before.channel.id in self.join_to_create_channel_ids:
            return

        # User joined a voice channel
        if after.channel and after.channel.id in self.join_to_create_channel_ids:
            if not self.voice_category_id:
                logger.error("Voice setup is incomplete. Please run /voice setup command.")
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
                category = self.bot.get_channel(self.voice_category_id)
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
                    channel_name = self._get_user_game_name(member) or f"{member.display_name}'s Channel"
                channel_name = channel_name[:32]  # Ensure name is within 32 characters

                # Determine user limit
                user_limit = settings_row[1] if settings_row and settings_row[1] else None

                # Create the channel with the settings
                overwrites = {
                    member: discord.PermissionOverwrite(manage_channels=True, connect=True)
                }
                new_channel = await member.guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    user_limit=user_limit,
                    overwrites=overwrites
                )

                # Apply saved permissions (like PTT settings)
                if settings_row and settings_row[2]:
                    permissions = json.loads(settings_row[2])
                    await self._apply_channel_permissions(new_channel, permissions)

                # Move the member to the new channel
                await member.move_to(new_channel)

                # Store channel in the database
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

                # Delete the channel after it's empty
                await new_channel.delete()
                async with Database.get_connection() as db:
                    await db.execute("DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (new_channel.id,))
                    await db.commit()
                    logger.info(f"Deleted voice channel '{new_channel.name}'")
            except Exception as e:
                logger.exception(f"Error creating voice channel for {member.display_name}: {e}")

    async def _wait_for_channel_empty(self, channel):
        """
        Waits until the voice channel is empty before proceeding.
        """
        while True:
            await asyncio.sleep(5)
            if len(channel.members) == 0:
                break

    def _get_user_game_name(self, member):
        """
        Retrieves the name of the game the user is currently playing.
        """
        for activity in member.activities:
            if isinstance(activity, discord.Game):
                return activity.name
        return None

    async def _apply_channel_permissions(self, channel, permissions):
        """
        Applies saved permissions to the channel.
        """
        guild = channel.guild
        # Apply PTT settings
        ptt_settings = permissions.get('ptt')
        if ptt_settings:
            await apply_ptt_settings(channel, ptt_settings)

        # Apply other permissions (permit/reject)
        perm_settings = permissions.get('permissions')
        if perm_settings:
            await apply_permissions_changes(channel, perm_settings)

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
                voice_channel = await interaction.guild.create_voice_channel(channel_name, category=category)
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
        channel = await self._get_user_channel(member)
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
        channel = await self._get_user_channel(member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Send the TargetTypeSelectView
        view = TargetTypeSelectView(self.bot, member, action="reject")
        await interaction.response.send_message("Choose the type of target you want to reject:", view=view, ephemeral=True)

    @app_commands.command(name="force_ptt", description="Enable PTT for users/roles in your channel")
    @app_commands.guild_only()
    async def force_ptt(self, interaction: discord.Interaction):
        """
        Enables PTT (push-to-talk) for users or roles in the user's voice channel.
        """
        member = interaction.user
        channel = await self._get_user_channel(member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Send the TargetTypeSelectView with 'force_ptt' action
        view = TargetTypeSelectView(self.bot, member, action="force_ptt")
        await interaction.response.send_message("Choose the type of target you want to enable PTT for:", view=view, ephemeral=True)

    @app_commands.command(name="disable_ptt", description="Disable PTT for users/roles in your channel")
    @app_commands.guild_only()
    async def disable_ptt(self, interaction: discord.Interaction):
        """
        Disables PTT (push-to-talk) for users or roles in the user's voice channel.
        """
        member = interaction.user
        channel = await self._get_user_channel(member)
        if not channel:
            await interaction.response.send_message("You don't own a channel.", ephemeral=True)
            return

        # Send the TargetTypeSelectView with 'disable_ptt' action
        view = TargetTypeSelectView(self.bot, member, action="disable_ptt")
        await interaction.response.send_message("Choose the type of target you want to disable PTT for:", view=view, ephemeral=True)

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
        channel = await self._get_user_channel(member)
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
                (member.id,)
            )
            settings_row = await cursor.fetchone()
            permissions = {}
            if settings_row and settings_row[0]:
                permissions = json.loads(settings_row[0])

            permissions['lock'] = lock

            await db.execute(
                "INSERT OR REPLACE INTO channel_settings (user_id, permissions) VALUES (?, ?)",
                (member.id, json.dumps(permissions))
            )
            await db.commit()

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
        channel = await self._get_user_channel(member)
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
            "/voice force_ptt - Enable PTT for users/roles in your channel\n"
            "/voice disable_ptt - Disable PTT for users/roles in your channel\n"
            "/voice close - Close your voice channel\n"
            "/voice reset - Reset your channel settings to default\n"
            "/voice help - Show this help message"
        )
        await interaction.response.send_message(help_text, ephemeral=True)

    async def _get_user_channel(self, member):
        """
        Retrieves the voice channel owned by the user.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT voice_channel_id FROM user_voice_channels WHERE user_id = ?", (member.id,))
            row = await cursor.fetchone()
            if not row:
                return None
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            return channel

    async def _reset_current_channel_settings(self, member):
        """
        Resets the settings of the user's current voice channel to default.
        """
        channel = await self._get_user_channel(member)
        if not channel:
            return

        # Reset channel name
        default_name = f"{member.display_name}'s Channel"
        await channel.edit(name=default_name[:32], user_limit=None)

        # Reset permissions
        await reset_channel_permissions(channel)

        # Remove settings from the database
        async with Database.get_connection() as db:
            await db.execute("DELETE FROM channel_settings WHERE user_id = ?", (member.id,))
            await db.commit()

        logger.info(f"Reset settings for {member.display_name}'s channel.")

async def setup(bot):
    await bot.add_cog(Voice(bot))
    logger.info("Voice cog loaded.")
