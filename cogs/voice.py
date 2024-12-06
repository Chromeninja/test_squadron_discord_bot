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
from helpers.modals import ResetSettingsConfirmationModal, NameModal, LimitModal
from helpers.permissions_helper import update_channel_owner
from helpers.voice_utils import (
    get_user_channel,
    get_user_game_name,
    update_channel_settings,
    safe_create_voice_channel,
    safe_move_member,
    safe_delete_channel,
    safe_edit_channel,
    get_channel_permissions,
    get_ptt_settings
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
        self.lead_moderator_role_ids = [int(role_id) for role_id in self.config['roles'].get('lead_moderators', [])]
        self.cooldown_seconds = self.config['voice'].get('cooldown_seconds', 60)
        self.join_to_create_channel_ids = []
        self.voice_category_id = None
        self.managed_voice_channels = set()
        self.last_channel_edit = {}

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
        if before.channel and before.channel.id in self.managed_voice_channels:
            async with Database.get_connection() as db:
                cursor = await db.execute("SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?", (before.channel.id,))
                row = await cursor.fetchone()
                owner_id = row[0] if row else None
            if len(before.channel.members) == 0:
                # Channel is empty, delete it
                await safe_delete_channel(before.channel)
                self.managed_voice_channels.remove(before.channel.id)
                async with Database.get_connection() as db:
                    await db.execute("DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (before.channel.id,))
                    await db.commit()
                logger.info(f"Deleted empty voice channel '{before.channel.name}'")
            else:
                # Owner left but channel still has members
                if member.id == owner_id:
                    logger.info(f"Owner '{member.display_name}' left '{before.channel.name}'. Ownership can be claimed.")

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
                # Get the "Join to Create" channel that the user joined
                join_to_create_channel = after.channel  # This is the "Join to Create" channel

                # Retrieve saved settings or set defaults
                async with Database.get_connection() as db:
                    cursor = await db.execute("SELECT channel_name, user_limit, lock FROM channel_settings WHERE user_id = ?", (member.id,))
                    settings_row = await cursor.fetchone()

                # Determine channel name
                if settings_row and settings_row[0]:
                    channel_name = settings_row[0]
                else:
                    channel_name = get_user_game_name(member) or f"{member.display_name}'s Channel"
                channel_name = channel_name[:32]  # Ensure name is within 32 characters

                # Clone the "Join to Create" channel with the new name
                new_channel = await join_to_create_channel.clone(name=channel_name)

                # Set user limit if specified
                if settings_row and settings_row[1] is not None:
                    user_limit = settings_row[1]
                    await new_channel.edit(user_limit=user_limit)
                else:
                    user_limit = None

                # Adjust permissions
                overwrites = new_channel.overwrites
                # Ensure the owner has manage_channels and connect permissions
                overwrites[member] = discord.PermissionOverwrite(manage_channels=True, connect=True)
                # Update the overwrites
                await new_channel.edit(overwrites=overwrites)

                # Apply DB-stored permissions and PTT
                await self._apply_channel_permissions(new_channel, member.id)

                # Move the member to the new channel
                await safe_move_member(member, new_channel)

                # Store channel in the database and in-memory set
                async with Database.get_connection() as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO user_voice_channels (voice_channel_id, owner_id) VALUES (?, ?)",
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
                    view = ChannelSettingsView(self.bot)
                    await new_channel.send(f"{member.mention}, configure your channel settings:", view=view)
                except discord.Forbidden:
                    logger.warning(f"Cannot send message to '{new_channel.name}'.")
                except Exception as e:
                    logger.exception(f"Error sending settings view to '{new_channel.name}': {e}")

                # Wait until the channel is empty
                await self._wait_for_channel_empty(new_channel)
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

    async def _apply_channel_permissions(self, channel: discord.VoiceChannel, owner_id: int):
        """
        Applies saved permissions to the channel.

        Args:
            channel (discord.VoiceChannel): The channel to modify.
            permissions (dict): The permissions to apply.
        """
        permissions = await get_channel_permissions(owner_id)
        ptt_settings = await get_ptt_settings(owner_id)

        original_overwrites = channel.overwrites.copy()  # Store original
        overwrites = channel.overwrites.copy()

        # Apply permit/reject
        for target_id, target_type, permission in permissions:
            if target_type == 'user':
                target = channel.guild.get_member(target_id)
            elif target_type == 'role':
                target = channel.guild.get_role(target_id)
            else:
                continue

            if target:
                overwrite = overwrites.get(target, discord.PermissionOverwrite())
                overwrite.connect = (permission == 'permit')
                overwrites[target] = overwrite

        # Apply PTT
        for target_id, target_type, ptt_enabled in ptt_settings:
            if target_type == 'user':
                target = channel.guild.get_member(target_id)
            elif target_type == 'role':
                target = channel.guild.get_role(target_id)
            elif target_type == 'everyone':
                target = channel.guild.default_role
            else:
                continue

            if target:
                overwrite = overwrites.get(target, discord.PermissionOverwrite())
                overwrite.use_voice_activation = not ptt_enabled
                overwrites[target] = overwrite

        # Ensure owner permissions
        owner = channel.guild.get_member(owner_id)
        if owner:
            overwrite = overwrites.get(owner, discord.PermissionOverwrite())
            overwrite.manage_channels = True
            overwrite.connect = True
            overwrites[owner] = overwrite

        # Now check if anything actually changed
        if overwrites == original_overwrites:
            logger.info(f"No overwrite changes for channel '{channel.name}', skipping edit.")
            return

        # Optional: Add a cooldown to prevent rapid repeated edits
        now = time.time()
        last_edit = self.last_channel_edit.get(channel.id, 0)
        if now - last_edit < 2:  # e.g., at least 2 seconds between edits
            logger.info(f"Skipping channel edit for '{channel.name}' due to cooldown.")
            return

        # If we reached here, changes are real and no cooldown block
        try:
            await safe_edit_channel(channel, overwrites=overwrites)
            logger.info(f"Applied permissions to channel '{channel.name}'.")
            self.last_channel_edit[channel.id] = now
        except Exception as e:
            logger.error(f"Failed to apply permissions to channel '{channel.name}': {e}")
            raise

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
            await interaction.followup.send("Failed to create voice channels. Check bot permissions.", ephemeral=True)

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
        view = TargetTypeSelectView(self.bot, action="permit")
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

        view = TargetTypeSelectView(self.bot, action="reject")
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
        view = PTTSelectView(self.bot)
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
        original_overwrites = channel.overwrites.copy()
        overwrites = channel.overwrites.copy()
        default_role = interaction.guild.default_role

        overwrite = overwrites.get(default_role, discord.PermissionOverwrite())
        overwrite.connect = not lock
        overwrites[default_role] = overwrite

        # Check if anything changed
        if overwrites == original_overwrites:
            logger.info(f"No change in lock state for '{channel.name}', skipping update.")
            await interaction.response.send_message("Channel lock state unchanged.", ephemeral=True)
            return

        # Check cooldown
        now = time.time()
        last_edit = self.last_channel_edit.get(channel.id, 0)
        if now - last_edit < 2:
            logger.info(f"Skipping channel edit for '{channel.name}' due to cooldown.")
            await interaction.response.send_message("Channel update skipped due to cooldown.", ephemeral=True)
            return  
        
        # Apply the permission changes with rate limiting
        try:
            await safe_edit_channel(channel, overwrites=overwrites)
        except Exception:
            await interaction.response.send_message("Failed to update channel permissions.", ephemeral=True)
            return

        # Update lock state in channel_settings
        self.last_channel_edit[channel.id] = now
        await update_channel_settings(member.id, lock=1 if lock else 0)
        status = "locked" if lock else "unlocked"
        await interaction.response.send_message(f"Your voice channel has been {status}.", ephemeral=True)
        logger.info(f"{member.display_name} {status} their voice channel.")

    @app_commands.command(name="name", description="Change your voice channel's name")
    @app_commands.guild_only()
    async def rename_voice(self, interaction: discord.Interaction):
        """
        Changes the user's voice channel name.
        """
        await interaction.response.send_modal(NameModal(self.bot))

    @app_commands.command(name="limit", description="Set user limit for your voice channel")
    @app_commands.guild_only()
    async def set_limit_voice(self, interaction: discord.Interaction):
        """
        Sets the user limit for the user's voice channel.
        """
        await interaction.response.send_modal(LimitModal(self.bot))

    @app_commands.command(name="reset", description="Reset your channel settings to default")
    @app_commands.guild_only()
    async def reset_channel_settings(self, interaction: discord.Interaction):
        """
        Resets the user's channel settings to default.
        """
        await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot))

    @app_commands.command(name="claim", description="Claim ownership of the voice channel if the owner is absent")
    @app_commands.guild_only()
    async def claim_channel(self, interaction: discord.Interaction):
        """
        Allows a user to claim ownership of a voice channel if the original owner has left.
        """
        member = interaction.user
        channel = member.voice.channel if member.voice else None
        if not channel:
            await interaction.response.send_message("You are not connected to any voice channel.", ephemeral=True)
            return

        # Check if the channel is managed by the bot
        if channel.id not in self.managed_voice_channels:
            await interaction.response.send_message("This channel cannot be claimed.", ephemeral=True)
            return

        # Fetch current owner from the database
        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?", (channel.id,))
            row = await cursor.fetchone()
            if row:
                owner_id = row[0]
            else:
                await interaction.response.send_message("Unable to retrieve channel ownership information.", ephemeral=True)
                return

        # Check if the owner is still in the channel
        owner_in_channel = any(user.id == owner_id for user in channel.members)
        if owner_in_channel:
            logger.warning(f"{member.display_name} attempted to claim '{channel.name}' but owner is present.")
            await interaction.response.send_message("The channel owner is still present. You cannot claim ownership.", ephemeral=True)
            return

        # Update the owner in the database
        async with Database.get_connection() as db:
            await db.execute("UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?", (member.id, channel.id))
            await db.commit()
        # After updating the owner in the database and permissions
        try:
            view = ChannelSettingsView(self.bot)
            await channel.send(f"{member.mention}, configure your channel settings:", view=view)
        except discord.Forbidden:
            logger.warning(f"Cannot send message to '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Error sending settings view to '{channel.name}': {e}")

        # Use the helper function to update permissions
        try:
            await update_channel_owner(channel, member.id, owner_id)
            await interaction.response.send_message(f"You have claimed ownership of '{channel.name}'.", ephemeral=True)
            logger.info(f"{member.display_name} claimed ownership of '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Failed to claim ownership: {e}")
            await interaction.response.send_message("Failed to claim ownership of the channel.", ephemeral=True)

    @app_commands.command(name="help", description="Show help for voice commands")
    @app_commands.guild_only()
    async def voice_help(self, interaction: discord.Interaction):
        """
        Displays help information for voice commands.
        """
        commands_list = []
        for command in self.walk_app_commands():
            if command.parent is self:
                commands_list.append(f"/voice {command.name} - {command.description}")

        help_text = "**Voice Commands:**\n" + "\n".join(commands_list)
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

        # Get the "Join to Create" channel
        join_to_create_channel = self.bot.get_channel(self.join_to_create_channel_ids[0])  # Use the first one or select appropriately
        if not join_to_create_channel:
            logger.error("Join to Create channel not found.")
            return

        # Get settings from "Join to Create" channel
        default_overwrites = join_to_create_channel.overwrites
        default_user_limit = join_to_create_channel.user_limit
        default_bitrate = join_to_create_channel.bitrate

        # Reset the channel's settings
        try:
            default_name = f"{member.display_name}'s Channel"[:32]

            # Copy the overwrites and ensure the owner has the correct permissions
            overwrites = default_overwrites.copy()
            overwrites[member] = discord.PermissionOverwrite(manage_channels=True, connect=True)

            await channel.edit(
                name=default_name,
                overwrites=overwrites,
                user_limit=default_user_limit,
                bitrate=default_bitrate
            )
            logger.info(f"Reset channel settings for '{member.display_name}'")
        except Exception as e:
            logger.exception(f"Failed to reset channel settings for {member.display_name}: {e}")
            return

        # Reset settings to defaults
        await update_channel_settings(member.id, channel_name=None, user_limit=None, lock=0)
        logger.info(f"Reset settings for {member.display_name}'s channel.")
    ### Admin Commands

    def is_bot_admin_or_lead_moderator(self, member):
        roles = [role.id for role in member.roles]
        return any(role_id in roles for role_id in (self.bot_admin_role_ids + self.lead_moderator_role_ids))

    @app_commands.command(name="admin_reset", description="Admin command to reset a user's voice channel")
    @app_commands.guild_only()
    async def admin_reset_voice(self, interaction: discord.Interaction, user: discord.Member):
        """
        Allows bot admins or lead moderators to reset a user's voice channel.
        """
        # Permission check
        if not self.is_bot_admin_or_lead_moderator(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        # Check if the user has a channel
        channel = await get_user_channel(self.bot, user)
        if not channel:
            await interaction.response.send_message(f"{user.display_name} does not own a voice channel.", ephemeral=True)
            return

        # Reset the user's channel settings
        await self._reset_current_channel_settings(user)
        await interaction.response.send_message(f"{user.display_name}'s voice channel has been reset to default settings.", ephemeral=True)
        logger.info(f"{interaction.user.display_name} reset {user.display_name}'s voice channel.")

    @app_commands.command(name="owner", description="List all voice channels managed by the bot and their owners")
    @app_commands.guild_only()
    async def voice_owner(self, interaction: discord.Interaction):
        """
        Lists all voice channels managed by the bot and their owners.
        """
        # Fetch all managed voice channels from the database
        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT voice_channel_id, owner_id FROM user_voice_channels")
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("There are no active voice channels managed by the bot.", ephemeral=True)
            return

        message = "**Active Voice Channels Managed by the Bot:**\n"
        for channel_id, owner_id in rows:
            channel = self.bot.get_channel(channel_id)
            owner = interaction.guild.get_member(owner_id)
            if channel and owner:
                message += f"- {channel.name} (Owner: {owner.display_name})\n"
            elif channel:
                message += f"- {channel.name} (Owner: Unknown)\n"
            else:
                # Channel might have been deleted; remove it from the database
                async with Database.get_connection() as db:
                    await db.execute("DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (channel_id,))
                    await db.commit()
                self.managed_voice_channels.discard(channel_id)

        await interaction.response.send_message(message, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Voice(bot))
    logger.info("Voice cog loaded.")
