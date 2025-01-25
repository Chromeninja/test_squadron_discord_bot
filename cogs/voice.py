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
from helpers.views import ChannelSettingsView, TargetTypeSelectView, PTTSelectView
from helpers.modals import ResetSettingsConfirmationModal, NameModal, LimitModal
from helpers.permissions_helper import update_channel_owner
from helpers.voice_utils import (
    get_user_channel,
    get_user_game_name,
    update_channel_settings,
    get_channel_permissions,
    get_ptt_settings,
    get_priority_speaker_settings,
    get_soundboard_settings,
    fetch_channel_settings,
    format_channel_settings,
)
from helpers.discord_api import (
    create_voice_channel,
    delete_channel,
    edit_channel,
    move_member,
    send_message,
    followup_send_message,
    channel_send_message,
    send_direct_message
)

logger = get_logger(__name__)

class Voice(commands.GroupCog, name="voice"):
    """
    Cog for managing dynamic voice channels.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.bot_admin_role_ids = [int(r) for r in self.config['roles'].get('bot_admins', [])]
        self.lead_moderator_role_ids = [int(r) for r in self.config['roles'].get('lead_moderators', [])]
        self.cooldown_seconds = self.config['voice'].get('cooldown_seconds', 60)
        self.expiry_days = self.config['voice'].get('expiry_days', 30)
        self.join_to_create_channel_ids = []
        self.voice_category_id = None
        self.managed_voice_channels = set()
        self.last_channel_edit = {}

    async def cog_load(self):
        """
        Called when the cog is loaded.
        Fetches stored settings and deletes previously managed voice channels.
        Also starts the cleanup task for expired voice channel data.
        """

        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", ('join_to_create_channel_ids',))
            if row := await cursor.fetchone():
                self.join_to_create_channel_ids = json.loads(row[0])

            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", ('voice_category_id',))
            if row := await cursor.fetchone():
                self.voice_category_id = int(row[0])

            cursor = await db.execute("SELECT voice_channel_id FROM user_voice_channels")
            rows = await cursor.fetchall()

            for (channel_id,) in rows:
                self.bot.loop.create_task(self.cleanup_voice_channel(channel_id))

        logger.info("Voice cog loaded with 'delete all managed channels' configuration.")

        # Start the cleanup task for expired voice channel data
        self.bot.loop.create_task(self.channel_data_cleanup_loop())
        logger.info("Started voice channel data cleanup task.")

    async def cleanup_voice_channel(self, channel_id):
        """
        Deletes a voice channel and removes it from the database.
        """
        async with Database.get_connection() as db:
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                
                if channel:
                    logger.info(f"Deleting managed voice channel: {channel.name} (ID: {channel.id})")
                    await channel.delete()
                else:
                    logger.warning(f"Channel with ID {channel_id} not found.")

            except discord.NotFound:
                logger.warning(f"Channel with ID {channel_id} not found; assumed already deleted.")
            except discord.Forbidden:
                logger.error(f"Bot lacks permissions to delete channel ID {channel_id}.")
            except discord.HTTPException as e:
                logger.error(f"HTTP exception occurred while deleting channel ID {channel_id}: {e}")
            finally:
                # Remove the channel from the database
                await db.execute("DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (channel_id,))
                await db.commit()
                logger.info(f"Removed channel ID {channel_id} from the database.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Handles voice state updates:
        - If a user leaves a managed channel and it is empty, deletes it.
        - If a user joins a 'Join to Create' channel, creates a managed channel.
        """
        logger.debug(f"Voice state update for {member.display_name}: before={before.channel}, after={after.channel}")

        # User leaves a managed channel
        if before.channel and before.channel.id in self.managed_voice_channels:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                    (before.channel.id,)
                )
                row = await cursor.fetchone()
                owner_id = row[0] if row else None

                if len(before.channel.members) == 0:
                    # Channel is empty, delete it
                    await delete_channel(before.channel)
                    self.managed_voice_channels.remove(before.channel.id)
                    await db.execute(
                        "DELETE FROM user_voice_channels WHERE voice_channel_id = ?",
                        (before.channel.id,)
                    )
                    await db.commit()
                    logger.info(f"Deleted empty voice channel '{before.channel.name}'")
                else:
                    # Owner left but channel still has members
                    if member.id == owner_id:
                        logger.info(f"Owner '{member.display_name}' left '{before.channel.name}'. Ownership can be claimed.")

        # User joins a 'Join to Create' channel
        if after.channel and after.channel.id in self.join_to_create_channel_ids:
            if not self.voice_category_id:
                logger.error("Voice setup is incomplete. Please run /voice setup command.")
                return

            # Prevent loops if user is already in a managed channel
            if member.voice and member.voice.channel and member.voice.channel.id in self.managed_voice_channels:
                logger.debug(f"User '{member.display_name}' is already in a managed channel. Skipping creation.")
                return

            # Check cooldown for creating channels
            current_time = int(time.time())
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT last_created FROM voice_cooldowns WHERE user_id = ?", (member.id,)
                )
                cooldown_row = await cursor.fetchone()
                if cooldown_row:
                    last_created = cooldown_row[0]
                    elapsed_time = current_time - last_created
                    if elapsed_time < self.cooldown_seconds:
                        remaining_time = self.cooldown_seconds - elapsed_time
                        try:
                            await send_direct_message(
                                member,
                                f"You're creating channels too quickly. Please wait {remaining_time} seconds."
                            )
                        except Exception as e:
                            logger.warning(f"Failed to DM {member.display_name}: {e}")
                        return

            # Create the voice channel
            try:
                join_to_create_channel = after.channel
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT channel_name, user_limit, lock FROM channel_settings WHERE user_id = ?",
                        (member.id,)
                    )
                    settings_row = await cursor.fetchone()

                # Determine channel name
                if settings_row and settings_row[0]:
                    channel_name = settings_row[0]
                else:
                    channel_name = get_user_game_name(member) or f"{member.display_name}'s Channel"
                channel_name = channel_name[:32]

                new_channel = await join_to_create_channel.clone(name=channel_name)

                # Prepare edits in one go
                edit_kwargs = {}
                overwrites = new_channel.overwrites.copy()
                overwrites[member] = discord.PermissionOverwrite(manage_channels=True, connect=True)

                if settings_row and settings_row[1] is not None:
                    edit_kwargs['user_limit'] = settings_row[1]

                edit_kwargs['overwrites'] = overwrites

                await move_member(member, new_channel)
                await edit_channel(new_channel, **edit_kwargs)

                # Store channel and cooldown
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

                # Apply permissions, PTT, Priority Speaker, and Soundboard
                await self._apply_channel_permissions(new_channel, member.id)

                # Apply lock if enabled
                if settings_row and settings_row[2] == 1:
                    lock_overwrites = new_channel.overwrites.copy()
                    default_role = new_channel.guild.default_role
                    overwrite = lock_overwrites.get(default_role, discord.PermissionOverwrite())
                    overwrite.connect = False
                    lock_overwrites[default_role] = overwrite
                    await edit_channel(new_channel, overwrites=lock_overwrites)
                    logger.info(
                        f"Re-applied lock setting for {member.display_name}'s channel: '{new_channel.name}'."
                    )

                # Send settings view
                try:
                    view = ChannelSettingsView(self.bot)
                    await channel_send_message(
                        new_channel,
                        f"{member.mention}, configure your channel settings:",
                        view=view
                    )
                except discord.Forbidden:
                    logger.warning(f"Cannot send message to '{new_channel.name}'.")
                except Exception as e:
                    logger.exception(f"Error sending settings view to '{new_channel.name}': {e}")

                # Wait until the channel is empty
                await self._wait_for_channel_empty(new_channel)
            except Exception as e:
                logger.exception(f"Error creating voice channel for {member.display_name}: {e}")

    async def channel_data_cleanup_loop(self):
        """
        Runs immediately, then every 24 hours to remove stale data
        if last_created is older than expiry_days.
        """
        await self.cleanup_stale_channel_data()

        while not self.bot.is_closed():
            await asyncio.sleep(24 * 60 * 60)  # 24 hours
            await self.cleanup_stale_channel_data()

    async def cleanup_stale_channel_data(self):
        """
        Removes users' voice channel data if last_created is older
        than config['voice']['expiry_days']. No channel deletion here.
        """
        expiry_seconds = self.expiry_days * 24 * 60 * 60
        cutoff_time = time.time() - expiry_seconds

        logger.info(f"Running stale channel data cleanup (cutoff={cutoff_time}).")

        async with Database.get_connection() as db:
            cursor = await db.execute("""
                SELECT user_id 
                FROM voice_cooldowns
                WHERE last_created < ?
            """, (cutoff_time,))
            rows = await cursor.fetchall()
            stale_user_ids = [row[0] for row in rows]

            if not stale_user_ids:
                logger.info("No stale voice channel data found.")
                return

            logger.info(f"Found {len(stale_user_ids)} stale user(s) to clean up.")

            tables_to_delete = [
                ("user_voice_channels", "owner_id"),
                ("channel_settings", "user_id"),
                ("channel_permissions", "user_id"),
                ("channel_ptt_settings", "user_id"),
                ("channel_priority_speaker_settings", "user_id"),
                ("channel_soundboard_settings", "user_id"),
                ("voice_cooldowns", "user_id"),
            ]

            for user_id in stale_user_ids:
                try:
                    for table, column in tables_to_delete:
                        await db.execute(f"DELETE FROM {table} WHERE {column} = ?", (user_id,))

                    logger.info(f"Cleaned stale data for user_id={user_id}")

                except Exception as e:
                    logger.exception(f"Error cleaning stale data for user_id={user_id}: {e}")

            await db.commit()

        logger.info("Stale channel data cleanup completed.")

    async def _wait_for_channel_empty(self, channel: discord.VoiceChannel):
        """
        Waits until the voice channel is empty before continuing.
        """
        while True:
            await asyncio.sleep(5)
            if len(channel.members) == 0:
                break

    async def _apply_channel_permissions(self, channel: discord.VoiceChannel, owner_id: int):
        """
        Applies saved permissions (permit/reject), PTT, Priority Speaker, and Soundboard
        to the channel in one edit.
        """
        permissions = await get_channel_permissions(owner_id)
        ptt_settings = await get_ptt_settings(owner_id)
        priority_settings = await get_priority_speaker_settings(owner_id)
        soundboard_settings = await get_soundboard_settings(owner_id)

        original_overwrites = channel.overwrites.copy()
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

        for target_id, target_type, priority_enabled in priority_settings:
            if target_type == 'user':
                target = channel.guild.get_member(target_id)
            elif target_type == 'role':
                target = channel.guild.get_role(target_id)
            else:
                continue
            if target:
                overwrite = overwrites.get(target, discord.PermissionOverwrite())
                overwrite.priority_speaker = priority_enabled
                overwrites[target] = overwrite

        for target_id, target_type, soundboard_enabled in soundboard_settings:
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
                overwrite.use_soundboard = soundboard_enabled
                overwrites[target] = overwrite

        # Ensure owner permissions
        owner = channel.guild.get_member(owner_id)
        if owner:
            overwrite = overwrites.get(owner, discord.PermissionOverwrite())
            overwrite.manage_channels = True
            overwrite.connect = True
            overwrites[owner] = overwrite

        if overwrites == original_overwrites:
            logger.info(f"No overwrite changes for channel '{channel.name}', skipping edit.")
            return

        now = time.time()
        last_edit = self.last_channel_edit.get(channel.id, 0)
        if now - last_edit < 2:
            logger.info(f"Skipping channel edit for '{channel.name}' due to cooldown.")
            return

        try:
            await edit_channel(channel, overwrites=overwrites)
            logger.info(f"Applied permissions to channel '{channel.name}'.")
            self.last_channel_edit[channel.id] = now
        except Exception as e:
            logger.error(f"Failed to apply permissions to channel '{channel.name}': {e}")
            raise

    # -------------------------------------------------------------------------
    # Slash Commands
    # -------------------------------------------------------------------------

    @app_commands.command(name="setup", description="Set up the voice channel system.")
    @app_commands.guild_only()
    @app_commands.describe(category="Category to place voice channels in", num_channels="Number of 'Join to Create' channels")
    async def setup_voice(self, interaction: discord.Interaction, category: discord.CategoryChannel, num_channels: int):
        member = interaction.user
        if not any(r.id in self.bot_admin_role_ids for r in member.roles):
            await send_message(interaction, "Only bot admins can set up the bot.", ephemeral=True)
            return

        if not (1 <= num_channels <= 10):
            await send_message(interaction,
                "Please specify a number of channels between 1 and 10.", ephemeral=True
            )
            return

        await send_message(interaction, "Starting setup...", ephemeral=True)

        async with Database.get_connection() as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ('voice_category_id', str(category.id))
            )
            await db.commit()
        self.voice_category_id = category.id

        self.join_to_create_channel_ids = []
        try:
            for i in range(num_channels):
                ch_name = f"Join to Create #{i+1}" if num_channels > 1 else "Join to Create"
                voice_channel = await create_voice_channel(
                    guild=interaction.guild,
                    name=ch_name,
                    category=category
                )
                self.join_to_create_channel_ids.append(voice_channel.id)

            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ('join_to_create_channel_ids', json.dumps(self.join_to_create_channel_ids))
                )
                await db.commit()

            await send_message(interaction, "Setup complete!", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error creating voice channels: {e}")
            await followup_send_message(interaction,
                "Failed to create voice channels. Check bot permissions.", ephemeral=True
            )

    @app_commands.command(name="list", description="List all custom permissions and settings in your voice channel.")
    @app_commands.guild_only()
    async def list_channel_settings(self, interaction: discord.Interaction):
        settings = await fetch_channel_settings(self.bot, interaction)
        if not settings:
            return

        formatted = format_channel_settings(settings, interaction)

        embed = discord.Embed(
            title="Channel Settings & Permissions",
            description=f"Settings for your channel: {settings['channel_name']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="🔒 Lock State", value=settings["lock_state"], inline=True)
        embed.add_field(name="👥 User Limit", value=str(settings["user_limit"]), inline=True)
        embed.add_field(name="✅ Permits/Rejects", value="\n".join(formatted["permission_lines"]), inline=False)
        embed.add_field(name="🎙️ PTT Settings", value="\n".join(formatted["ptt_lines"]), inline=False)
        embed.add_field(name="📢 Priority Speaker", value="\n".join(formatted["priority_lines"]), inline=False)
        embed.add_field(name="🔊 Soundboard", value="\n".join(formatted["soundboard_lines"]), inline=False)
        embed.set_footer(text="Use /voice commands to adjust these settings.")

        await send_message(interaction, "", embed=embed, ephemeral=True)

    @app_commands.command(name="permit", description="Permit users/roles to join your channel.")
    @app_commands.guild_only()
    async def permit_user_voice(self, interaction: discord.Interaction):
        """
        Allows the channel owner to permit specific users or roles to join their channel.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        view = TargetTypeSelectView(self.bot, action="permit")
        await send_message(interaction,
            "Choose the type of target you want to permit:", view=view, ephemeral=True
        )

    @app_commands.command(name="reject", description="Reject users/roles from joining your channel.")
    @app_commands.guild_only()
    async def reject_user_voice(self, interaction: discord.Interaction):
        """
        Allows the channel owner to reject specific users or roles from joining their channel.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        view = TargetTypeSelectView(self.bot, action="reject")
        await send_message(interaction,
            "Choose the type of target you want to reject:", view=view, ephemeral=True
        )

    @app_commands.command(name="ptt", description="Manage PTT settings in your voice channel.")
    @app_commands.guild_only()
    async def ptt(self, interaction: discord.Interaction):
        """
        Allows the channel owner to manage PTT settings (enabling or disabling push-to-talk) for users or roles.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        view = PTTSelectView(self.bot)
        await send_message(interaction, "Do you want to enable or disable PTT?", view=view, ephemeral=True)

    @app_commands.command(name="lock", description="Lock your voice channel.")
    @app_commands.guild_only()
    async def lock_voice(self, interaction: discord.Interaction):
        """
        Locks the user's voice channel, preventing @everyone from connecting.
        """
        await self._change_channel_lock(interaction, lock=True)

    @app_commands.command(name="unlock", description="Unlock your voice channel.")
    @app_commands.guild_only()
    async def unlock_voice(self, interaction: discord.Interaction):
        """
        Unlocks the user's voice channel, allowing @everyone to connect.
        """
        await self._change_channel_lock(interaction, lock=False)

    async def _change_channel_lock(self, interaction: discord.Interaction, lock: bool):
        """
        Helper method to lock/unlock the channel by updating @everyone's connect permission.
        """
        member = interaction.user
        channel = await get_user_channel(self.bot, member)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        original_overwrites = channel.overwrites.copy()
        overwrites = channel.overwrites.copy()
        default_role = interaction.guild.default_role

        overwrite = overwrites.get(default_role, discord.PermissionOverwrite())
        overwrite.connect = not lock
        overwrites[default_role] = overwrite

        if overwrites == original_overwrites:
            logger.info(f"No change in lock state for '{channel.name}', skipping update.")
            await send_message(interaction, "Channel lock state unchanged.", ephemeral=True)
            return

        now = time.time()
        last_edit = self.last_channel_edit.get(channel.id, 0)
        if now - last_edit < 2:
            logger.info(f"Skipping channel edit for '{channel.name}' due to cooldown.")
            await send_message(interaction,
                "Channel update skipped due to cooldown.", ephemeral=True
            )
            return

        try:
            await edit_channel(channel, overwrites=overwrites)
        except Exception:
            await send_message(interaction, "Failed to update channel permissions.", ephemeral=True)
            return

        self.last_channel_edit[channel.id] = now
        await update_channel_settings(member.id, lock=1 if lock else 0)
        status = "locked" if lock else "unlocked"
        await send_message(interaction,
            f"Your voice channel has been {status}.", ephemeral=True
        )
        logger.info(f"{member.display_name} {status} their voice channel.")

    @app_commands.command(name="name", description="Change your voice channel's name.")
    @app_commands.guild_only()
    async def rename_voice(self, interaction: discord.Interaction):
        """
        Presents a modal to change the voice channel's name.
        """
        await interaction.response.send_modal(NameModal(self.bot))

    @app_commands.command(name="limit", description="Set user limit for your voice channel.")
    @app_commands.guild_only()
    async def set_limit_voice(self, interaction: discord.Interaction):
        """
        Presents a modal to set the user limit for the voice channel.
        """
        await interaction.response.send_modal(LimitModal(self.bot))

    @app_commands.command(name="reset", description="Reset your channel settings to default.")
    @app_commands.guild_only()
    async def reset_channel_settings(self, interaction: discord.Interaction):
        """
        Presents a modal to confirm resetting channel settings to defaults.
        """
        await interaction.response.send_modal(ResetSettingsConfirmationModal(self.bot))

    @app_commands.command(name="claim", description="Claim ownership of the voice channel if the owner is absent.")
    @app_commands.guild_only()
    async def claim_channel(self, interaction: discord.Interaction):
        """
        Allows a user to claim ownership of a channel if the original owner has left.
        """
        member = interaction.user
        channel = member.voice.channel if member.voice else None
        if not channel:
            await send_message(interaction,
                "You are not connected to any voice channel.", ephemeral=True
            )
            return

        if channel.id not in self.managed_voice_channels:
            await send_message(interaction, "This channel cannot be claimed.", ephemeral=True)
            return

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel.id,)
            )
            row = await cursor.fetchone()
            if not row:
                await send_message(interaction,
                    "Unable to retrieve channel ownership information.", ephemeral=True
                )
                return
            owner_id = row[0]

        owner_in_channel = any(u.id == owner_id for u in channel.members)
        if owner_in_channel:
            logger.warning(f"{member.display_name} attempted to claim '{channel.name}' but owner is present.")
            await send_message(interaction,
                "The channel owner is still present. You cannot claim ownership.", ephemeral=True
            )
            return

        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
                (member.id, channel.id)
            )
            await db.commit()

        try:
            view = ChannelSettingsView(self.bot)
            await channel.send(f"{member.mention}, configure your channel settings:", view=view)
        except discord.Forbidden:
            logger.warning(f"Cannot send message to '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Error sending settings view to '{channel.name}': {e}")

        try:
            await update_channel_owner(channel, member.id, owner_id)
            await send_message(interaction,
                f"You have claimed ownership of '{channel.name}'.", ephemeral=True
            )
            logger.info(f"{member.display_name} claimed ownership of '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Failed to claim ownership: {e}")
            await send_message(interaction,
                "Failed to claim ownership of the channel.", ephemeral=True
            )

    @app_commands.command(name="kick", description="Kick a user from your voice channel.")
    @app_commands.describe(user="The user you want to kick out.")
    @app_commands.guild_only()
    async def kick_user(self, interaction: discord.Interaction, user: discord.Member, reject: bool = False):
        """
        Disconnect a user from your channel. Optionally reject them from rejoining if `reject` is True.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if user not in channel.members:
            await send_message(interaction, f"{user.display_name} is not in your channel.", ephemeral=True)
            return

        # Kick (move to None)
        try:
            await user.move_to(None)
        except Exception as e:
            await send_message(interaction, f"Failed to kick {user.display_name}: {e}", ephemeral=True)
            return

        if not reject:
            await send_message(
                interaction,
                f"{user.display_name} has been kicked from your channel.",
                ephemeral=True
            )
            return

        # If reject == True, also deny connect perms so they can't rejoin:
        overwrites = channel.overwrites.copy()
        overwrite = overwrites.get(user, discord.PermissionOverwrite())
        overwrite.connect = False
        overwrites[user] = overwrite

        try:
            await edit_channel(channel, overwrites=overwrites)
            await send_message(
                interaction,
                f"{user.display_name} was kicked and temporarily rejected from rejoining.",
                ephemeral=True
            )
        except Exception as e:
            await send_message(
                interaction,
                f"User was kicked but failed to reject further: {e}",
                ephemeral=True
            )

    @app_commands.command(name="transfer", description="Transfer channel ownership to another user in your voice channel.")
    @app_commands.describe(new_owner="Who should be the new channel owner?")
    @app_commands.guild_only()
    async def transfer_ownership(self, interaction: discord.Interaction, new_owner: discord.Member):
        """
        Allows the current owner to transfer ownership to another user in the same channel.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if new_owner not in channel.members:
            await send_message(interaction,
                "The specified user must be in your channel to transfer ownership.",
                ephemeral=True
            )
            return

        # Update DB
        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
                (new_owner.id, channel.id)
            )
            await db.commit()

        # Update channel overwrites:
        overwrites = channel.overwrites.copy()
        # Remove manage_channels from old owner:
        old_overwrite = overwrites.get(interaction.user, None)
        if old_overwrite:
            old_overwrite.manage_channels = False
            overwrites[interaction.user] = old_overwrite

        # Grant manage_channels to new owner:
        new_ow = overwrites.get(new_owner, discord.PermissionOverwrite())
        new_ow.manage_channels = True
        new_ow.connect = True
        overwrites[new_owner] = new_ow

        try:
            await edit_channel(channel, overwrites=overwrites)
            await send_message(
                interaction,
                f"Channel ownership transferred to {new_owner.display_name}.",
                ephemeral=True
            )
            logger.info(
                f"{interaction.user.display_name} transferred ownership of '{channel.name}' "
                f"to {new_owner.display_name}."
            )
        except Exception as e:
            logger.exception(f"Failed to transfer ownership: {e}")
            await send_message(interaction, f"Failed to transfer ownership: {e}", ephemeral=True)

    @app_commands.command(name="help", description="Show help for voice commands.")
    @app_commands.guild_only()
    async def voice_help(self, interaction: discord.Interaction):
        """
        Displays a help embed with available voice commands.
        """
        excluded_commands = {"setup", "admin_reset","admin_list"}
        commands_list = []
        for command in self.walk_app_commands():
            if command.parent and command.parent.name == "voice" and command.name not in excluded_commands:
                commands_list.append(f"**/voice {command.name}** - {command.description}")

        if not commands_list:
            await send_message(interaction, "No voice commands available.", ephemeral=True)
            return

        help_text = "\n".join(commands_list)
        embed = discord.Embed(
            title="🎙️ Voice Commands Help",
            description=help_text,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Use these commands to manage your voice channels effectively.")

        await send_message(interaction, "", embed=embed, ephemeral=True)

    async def _reset_current_channel_settings(self, member: discord.Member):
        """
        Resets the user's channel settings to defaults using the first 'Join to Create' channel as a template.
        """
        channel = await get_user_channel(self.bot, member)
        if not channel:
            return

        if not self.join_to_create_channel_ids:
            logger.error("No join-to-create channel configured.")
            return
        join_to_create_channel = self.bot.get_channel(self.join_to_create_channel_ids[0])
        if not join_to_create_channel:
            logger.error("Join to Create channel not found.")
            return

        default_overwrites = join_to_create_channel.overwrites
        default_user_limit = join_to_create_channel.user_limit
        default_bitrate = join_to_create_channel.bitrate

        try:
            default_name = f"{member.display_name}'s Channel"[:32]
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

        await update_channel_settings(member.id, channel_name=None, user_limit=None, lock=0)
        logger.info(f"Reset settings for {member.display_name}'s channel.")

    def is_bot_admin_or_lead_moderator(self, member: discord.Member) -> bool:
        """
        Checks if a member is a bot admin or lead moderator.
        """
        roles = [r.id for r in member.roles]
        return any(r_id in roles for r_id in (self.bot_admin_role_ids + self.lead_moderator_role_ids))

    @app_commands.command(name="admin_reset", description="Admin command to reset a user's voice channel.")
    @app_commands.guild_only()
    async def admin_reset_voice(self, interaction: discord.Interaction, user: discord.Member):
        """
        Allows bot admins or lead moderators to reset a user's voice channel.
        """
        if not self.is_bot_admin_or_lead_moderator(interaction.user):
            await send_message(interaction, "You do not have permission to use this command.", ephemeral=True)
            return

        channel = await get_user_channel(self.bot, user)
        if not channel:
            await send_message(interaction,
                f"{user.display_name} does not own a voice channel.", ephemeral=True
            )
            return

        await self._reset_current_channel_settings(user)
        await send_message(interaction,
            f"{user.display_name}'s voice channel has been reset to default settings.", ephemeral=True
        )
        logger.info(f"{interaction.user.display_name} reset {user.display_name}'s voice channel.")

    @app_commands.command(name="owner", description="List all voice channels managed by the bot and their owners.")
    @app_commands.guild_only()
    async def voice_owner(self, interaction: discord.Interaction):
        """
        Lists all managed voice channels and their owners.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute("SELECT voice_channel_id, owner_id FROM user_voice_channels")
            rows = await cursor.fetchall()

        if not rows:
            await send_message(interaction,
                "There are no active voice channels managed by the bot.", ephemeral=True
            )
            return

        message = "**Active Voice Channels Managed by the Bot:**\n"
        for channel_id, owner_id in rows:
            channel = self.bot.get_channel(channel_id)
            owner = interaction.guild.get_member(owner_id)
            if channel and owner:
                message += f"- {channel.name} (Owner: {owner.display_name})\n"
            elif channel:
                message += f"- {channel.name} (Owner: Unknown)\n"
                async with Database.get_connection() as db:
                    await db.execute(
                        "DELETE FROM user_voice_channels WHERE voice_channel_id = ?", (channel_id,)
                    )
                    await db.commit()
                self.managed_voice_channels.discard(channel_id)

        await send_message(interaction, message, ephemeral=True)

    @app_commands.command(
        name="admin_list",
        description="View saved permissions and settings for a user's voice channel (Admins/Moderators only)."
    )
    @app_commands.guild_only()
    @app_commands.describe(user="The user whose voice channel settings you want to view.")
    async def admin_list_channel(self, interaction: discord.Interaction, user: discord.Member):
        """
        Allows an admin to view the saved voice channel settings and permissions for a specific user.
        """
        # Check if the user has the appropriate roles
        admin_role_ids = self.bot_admin_role_ids + self.lead_moderator_role_ids
        user_roles = [role.id for role in interaction.user.roles]
        if not any(role_id in user_roles for role_id in admin_role_ids):
            await send_message(interaction, "You do not have permission to use this command.", ephemeral=True)
            return

        # Fetch the saved channel settings for the user
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT channel_name, user_limit, lock FROM channel_settings WHERE user_id = ?",
                (user.id,)
            )
            row = await cursor.fetchone()

        if not row:
            await send_message(interaction, f"{user.display_name} does not have saved channel settings.", ephemeral=True)
            return

        # Extract settings from the database row
        channel_name = row[0] or f"{user.display_name}'s Channel"
        user_limit = row[1] or "No Limit"
        lock_state = "Locked" if row[2] == 1 else "Unlocked"

        # Fetch additional permissions and settings
        settings = {
            "channel_name": channel_name,
            "user_limit": user_limit,
            "lock_state": lock_state,
        }
        formatted = await self._format_admin_settings(user, interaction)

        # Build embed using `/voice list` format
        embed = discord.Embed(
            title=f"Saved Channel Settings & Permissions for {user.display_name}",
            description=f"Settings for the channel: {channel_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="🔒 Lock State", value=lock_state, inline=True)
        embed.add_field(name="👥 User Limit", value=str(user_limit), inline=True)
        embed.add_field(name="✅ Permits/Rejects", value="\n".join(formatted["permission_lines"]), inline=False)
        embed.add_field(name="🎙️ PTT Settings", value="\n".join(formatted["ptt_lines"]), inline=False)
        embed.add_field(name="📢 Priority Speaker", value="\n".join(formatted["priority_lines"]), inline=False)
        embed.add_field(name="🔊 Soundboard", value="\n".join(formatted["soundboard_lines"]), inline=False)
        embed.set_footer(text="Command restricted to admins and lead moderators.")

        await send_message(interaction, "", embed=embed, ephemeral=True)

    async def _format_admin_settings(self, user, interaction):
        """
        Helper method to format channel permissions and settings for an admin command.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT target_id, target_type, permission FROM channel_permissions WHERE user_id = ?",
                (user.id,)
            )
            perm_rows = await cursor.fetchall()

            cursor = await db.execute(
                "SELECT target_id, target_type, ptt_enabled FROM channel_ptt_settings WHERE user_id = ?",
                (user.id,)
            )
            ptt_rows = await cursor.fetchall()

            cursor = await db.execute(
                "SELECT target_id, target_type, priority_enabled FROM channel_priority_speaker_settings WHERE user_id = ?",
                (user.id,)
            )
            priority_rows = await cursor.fetchall()

            cursor = await db.execute(
                "SELECT target_id, target_type, soundboard_enabled FROM channel_soundboard_settings WHERE user_id = ?",
                (user.id,)
            )
            soundboard_rows = await cursor.fetchall()

        def format_target(target_id, target_type):
            if target_type == "user":
                target_user = interaction.guild.get_member(target_id)
                return target_user.mention if target_user else f"User ID: {target_id}"
            elif target_type == "role":
                target_role = interaction.guild.get_role(target_id)
                return target_role.mention if target_role else f"Role ID: {target_id}"
            elif target_type == "everyone":
                return "**Everyone**"
            return f"Unknown: {target_id}"

        permission_lines = [
            f"- {format_target(target_id, target_type)} => **{permission}**"
            for target_id, target_type, permission in perm_rows
        ] or ["No custom permissions set."]

        ptt_lines = [
            f"- {format_target(target_id, target_type)} => **PTT {'Enabled' if ptt_enabled else 'Disabled'}**"
            for target_id, target_type, ptt_enabled in ptt_rows
        ] or ["PTT is not configured."]

        priority_lines = [
            f"- {format_target(target_id, target_type)} => **PrioritySpeaker {'Enabled' if priority_enabled else 'Disabled'}**"
            for target_id, target_type, priority_enabled in priority_rows
        ] or ["No priority speakers set."]

        soundboard_lines = [
            f"- {format_target(target_id, target_type)} => **Soundboard {'Enabled' if sb_enabled else 'Disabled'}**"
            for target_id, target_type, sb_enabled in soundboard_rows
        ] or ["Soundboard settings not customized."]

        return {
            "permission_lines": permission_lines,
            "ptt_lines": ptt_lines,
            "priority_lines": priority_lines,
            "soundboard_lines": soundboard_lines,
        }


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
    logger.info("Voice cog loaded.")
