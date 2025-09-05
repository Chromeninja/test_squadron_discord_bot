# bot/cogs/voice_admin_cog.py
"""
Voice Admin Cog

This cog handles admin and user-facing voice commands including:
  - Voice channel settings management
  - Ownership transfer and claiming
  - Admin commands for setup and management
  - User commands for channel customization
"""

import json
import discord
from discord import app_commands
from discord.ext import commands

from config.config_loader import ConfigLoader
from helpers.database import Database
from helpers.discord_api import (
    send_message,
    edit_channel,
    delete_channel,
)
from helpers.logger import get_logger
from helpers.permissions_helper import (
    update_channel_owner,
)
from helpers.voice_utils import (
    get_user_channel,
    fetch_channel_settings,
    format_channel_settings,
    create_voice_settings_embed,
)
from bot.app.services.voice_service import JoinToCreateManager, VoiceSettingsService

logger = get_logger(__name__)


class VoiceAdminCog(commands.GroupCog, name="voice"):
    """
    Voice channel commands and administration.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.bot_admin_role_ids = [
            int(r) for r in self.config["roles"].get("bot_admins", [])
        ]
        self.lead_moderator_role_ids = [
            int(r) for r in self.config["roles"].get("lead_moderators", [])
        ]
        
        # Initialize voice services (will be injected by bot)
        self.jtc_manager: JoinToCreateManager = None
        self.settings_service: VoiceSettingsService = None
        
        # Dictionary to store JTC channels per guild (shared with runtime cog)
        self.guild_jtc_channels = {}
        # Dictionary to store voice categories per guild (shared with runtime cog)
        self.guild_voice_categories = {}
        
        # Legacy attributes (kept for backward compatibility)
        self.join_to_create_channel_ids = []
        self.voice_category_id = None

    def inject_voice_services(self, jtc_manager: JoinToCreateManager, settings_service: VoiceSettingsService):
        """Inject voice services after cog initialization."""
        self.jtc_manager = jtc_manager
        self.settings_service = settings_service
        logger.debug("Voice services injected into admin cog")

    async def cog_load(self):
        """Load configuration when cog is loaded."""
        # Load guild settings from the database (similar to runtime cog)
        async with Database.get_connection() as db:
            # Load guild-specific join-to-create channels
            cursor = await db.execute(
                "SELECT guild_id, key, value FROM guild_settings WHERE key = ?",
                ("join_to_create_channel_ids",),
            )
            rows = await cursor.fetchall()
            for row in rows:
                guild_id = row[0]
                value = json.loads(row[2])
                self.guild_jtc_channels[guild_id] = value
            
            # Load guild-specific voice categories
            cursor = await db.execute(
                "SELECT guild_id, key, value FROM guild_settings WHERE key = ?", 
                ("voice_category_id",)
            )
            rows = await cursor.fetchall()
            for row in rows:
                guild_id = row[0]
                value = int(row[2])
                self.guild_voice_categories[guild_id] = value
                
            # Fall back to legacy settings if no guild settings exist
            if not self.guild_jtc_channels:
                cursor = await db.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    ("join_to_create_channel_ids",),
                )
                if row := await cursor.fetchone():
                    self.join_to_create_channel_ids = json.loads(row[0])
                    # For legacy compatibility, add to first guild
                    if self.bot.guilds and self.join_to_create_channel_ids:
                        first_guild_id = self.bot.guilds[0].id
                        self.guild_jtc_channels[first_guild_id] = self.join_to_create_channel_ids

            if not self.guild_voice_categories:
                cursor = await db.execute(
                    "SELECT value FROM settings WHERE key = ?", ("voice_category_id",)
                )
                if row := await cursor.fetchone():
                    self.voice_category_id = int(row[0])
                    # For legacy compatibility, add to first guild
                    if self.bot.guilds and self.voice_category_id:
                        first_guild_id = self.bot.guilds[0].id
                        self.guild_voice_categories[first_guild_id] = self.voice_category_id

        logger.info("Voice admin cog loaded.")

    # ---------------------------
    # User Commands
    # ---------------------------

    @app_commands.command(
        name="list",
        description="List all custom permissions and settings in your voice channel.",
    )
    @app_commands.guild_only()
    async def list_channel_settings(self, interaction: discord.Interaction):
        """
        Lists the saved channel settings and permissions in an embed.
        """
        if self.settings_service:
            # Use the settings service
            settings = await self.settings_service.get_channel_settings(
                self.bot, interaction, interaction.guild.id, interaction.user.id
            )
        else:
            # Fallback to legacy method
            settings = await fetch_channel_settings(self.bot, interaction)
            
        if not settings:
            return
            
        if self.settings_service:
            formatted = await self.settings_service.format_settings_for_display(settings, interaction)
            embed = self.settings_service.create_settings_embed(
                settings=settings,
                formatted=formatted,
                title="Channel Settings & Permissions",
                footer="Use /voice commands or the dropdown menu to adjust these settings.",
            )
        else:
            # Legacy formatting
            formatted = format_channel_settings(settings, interaction)
            embed = create_voice_settings_embed(
                settings=settings,
                formatted=formatted,
                title="Channel Settings & Permissions",
                footer="Use /voice commands or the dropdown menu to adjust these settings.",
            )
        await send_message(interaction, "", embed=embed, ephemeral=True)

    @app_commands.command(
        name="claim",
        description="Claim ownership of the voice channel if the owner is absent.",
    )
    @app_commands.guild_only()
    async def claim_channel(self, interaction: discord.Interaction):
        """
        Allows a user to claim ownership of a voice channel if the original owner is absent.
        """
        member = interaction.user
        channel = member.voice.channel if member.voice else None
        if not channel:
            await send_message(
                interaction,
                "You are not connected to any voice channel.",
                ephemeral=True,
            )
            return

        # Check if this is a managed channel (we'll need to get this from runtime cog)
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel.id,),
            )
            row = await cursor.fetchone()
            if not row:
                await send_message(
                    interaction, "This channel cannot be claimed.", ephemeral=True
                )
                return

            current_owner_id = row[0]

        current_owner = interaction.guild.get_member(current_owner_id)
        if current_owner and current_owner in channel.members:
            await send_message(
                interaction,
                "The current owner is still in the channel.",
                ephemeral=True,
            )
            return

        try:
            await update_channel_owner(channel, member)
            await send_message(
                interaction,
                f"You have claimed ownership of '{channel.name}'.",
                ephemeral=True,
            )
            logger.info(f"{member.display_name} claimed ownership of '{channel.name}'.")
        except Exception as e:
            logger.exception(f"Failed to claim ownership: {e}")
            await send_message(
                interaction, "Failed to claim ownership of the channel.", ephemeral=True
            )

    @app_commands.command(
        name="transfer",
        description="Transfer channel ownership to another user in your voice channel.",
    )
    @app_commands.describe(new_owner="Who should be the new channel owner?")
    @app_commands.guild_only()
    async def transfer_ownership(
        self, interaction: discord.Interaction, new_owner: discord.Member
    ):
        """
        Transfers channel ownership to a specified member.
        """
        channel = await get_user_channel(self.bot, interaction.user)
        if not channel:
            await send_message(interaction, "You don't own a channel.", ephemeral=True)
            return

        if new_owner not in channel.members:
            await send_message(
                interaction,
                "The specified user must be in your channel to transfer ownership.",
                ephemeral=True,
            )
            return

        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE user_voice_channels SET owner_id = ? WHERE voice_channel_id = ?",
                (new_owner.id, channel.id),
            )
            await db.commit()

        overwrites = channel.overwrites.copy()
        if old_overwrite := overwrites.get(interaction.user, None):
            old_overwrite.manage_channels = False
            overwrites[interaction.user] = old_overwrite

        new_ow = overwrites.get(new_owner, discord.PermissionOverwrite())
        new_ow.manage_channels = True
        new_ow.connect = True
        overwrites[new_owner] = new_ow

        try:
            await edit_channel(
                channel,
                overwrites=overwrites,
                reason=f"Transferred ownership to {new_owner.display_name}",
            )
            await send_message(
                interaction,
                f"Transferred ownership of '{channel.name}' to {new_owner.display_name}.",
                ephemeral=True,
            )
            logger.info(
                f"{interaction.user.display_name} transferred ownership of '{channel.name}' to {new_owner.display_name}."
            )
        except Exception as e:
            logger.exception(f"Failed to transfer ownership: {e}")
            await send_message(
                interaction,
                "Failed to transfer ownership of the channel.",
                ephemeral=True,
            )

    @app_commands.command(name="help", description="Show help for voice commands.")
    @app_commands.guild_only()
    async def voice_help(self, interaction: discord.Interaction):
        """
        Displays help information for voice commands.
        """
        embed = discord.Embed(
            title="Voice Commands Help",
            description="Here are the available voice commands:",
            color=0x00FF00,
        )
        embed.add_field(
            name="/voice list",
            value="List all custom permissions and settings in your voice channel.",
            inline=False,
        )
        embed.add_field(
            name="/voice claim",
            value="Claim ownership of the voice channel if the owner is absent.",
            inline=False,
        )
        embed.add_field(
            name="/voice transfer",
            value="Transfer channel ownership to another user in your voice channel.",
            inline=False,
        )
        embed.add_field(
            name="Channel Settings",
            value="Use the dropdown menu in your voice channel for advanced settings like permissions, PTT, and more.",
            inline=False,
        )
        await send_message(interaction, "", embed=embed, ephemeral=True)

    @app_commands.command(
        name="owner",
        description="List all voice channels managed by the bot and their owners.",
    )
    @app_commands.guild_only()
    async def voice_owner(self, interaction: discord.Interaction):
        """
        Lists all managed voice channels and their owners.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT voice_channel_id, owner_id FROM user_voice_channels"
            )
            rows = await cursor.fetchall()

        if not rows:
            await send_message(
                interaction,
                "There are no active voice channels managed by the bot.",
                ephemeral=True,
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
                msg = (
                    f"Voice owner listing: channel '{channel.name}' (ID: {channel_id}) "
                    + "has no known owner; leaving DB entry for manual/admin review."
                )
                logger.info(msg)

        await send_message(interaction, message, ephemeral=True)

    # ---------------------------
    # Admin Commands
    # ---------------------------

    @app_commands.command(name="setup", description="Set up the voice channel system.")
    @app_commands.guild_only()
    @app_commands.describe(
        category="Category to place voice channels in",
        num_channels="Number of 'Join to Create' channels",
    )
    async def setup_voice(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        num_channels: int = 1,
    ):
        """
        Sets up the voice channel system by creating join-to-create channels.
        """
        if not self.is_bot_admin_or_lead_moderator(interaction.user):
            await send_message(
                interaction,
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        if num_channels < 1 or num_channels > 10:
            await send_message(
                interaction,
                "Number of channels must be between 1 and 10.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        created_channels = []

        try:
            # Create join-to-create channels
            for i in range(num_channels):
                channel_name = f"Join to Create {i + 1}" if num_channels > 1 else "Join to Create"
                jtc_channel = await interaction.guild.create_voice_channel(
                    channel_name,
                    category=category,
                    reason=f"Voice system setup by {interaction.user.display_name}"
                )
                created_channels.append(jtc_channel.id)

            # Store settings in database
            async with Database.get_connection() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
                    (guild_id, "join_to_create_channel_ids", json.dumps(created_channels)),
                )
                await db.execute(
                    "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
                    (guild_id, "voice_category_id", str(category.id)),
                )
                await db.commit()

            # Update local cache
            self.guild_jtc_channels[guild_id] = created_channels
            self.guild_voice_categories[guild_id] = category.id

            channel_list = ", ".join([f"<#{ch_id}>" for ch_id in created_channels])
            await send_message(
                interaction,
                f"Voice system set up successfully!\n"
                f"Join-to-Create channels: {channel_list}\n"
                f"Voice category: {category.mention}",
                ephemeral=True,
            )
            logger.info(f"Voice system set up by {interaction.user.display_name} in guild {guild_id}")

        except Exception as e:
            logger.exception(f"Error setting up voice system: {e}")
            await send_message(
                interaction,
                "Failed to set up the voice system. Please try again.",
                ephemeral=True,
            )

    def is_bot_admin_or_lead_moderator(self, member: discord.Member) -> bool:
        """Check if a member is a bot admin or lead moderator."""
        roles = [role.id for role in member.roles]
        return any(
            r_id in roles
            for r_id in (self.bot_admin_role_ids + self.lead_moderator_role_ids)
        )

    async def _reset_current_channel_settings(self, member: discord.Member, guild_id=None, jtc_channel_id=None):
        """
        Reset voice channel settings for a user.
        This is a stub implementation for now.
        """
        logger.debug(f"Resetting channel settings for {member.display_name} (stub)")
        # Future implementation will use the settings service

    async def _reset_all_user_settings(self, member: discord.Member):
        """
        Reset all voice channel settings for a user across all guilds.
        This is a stub implementation for now.
        """
        logger.debug(f"Resetting all settings for {member.display_name} (stub)")
        # Future implementation will use the settings service

    @app_commands.command(
        name="admin_reset", description="Admin command to reset a user's voice channel."
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user whose voice channel settings you want to reset.",
        jtc_channel="Specific join-to-create channel to reset settings for (optional).",
        global_reset="If true, reset this user's settings across all guilds and channels (destructive)."
    )
    async def admin_reset_voice(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        jtc_channel: discord.VoiceChannel = None,
        global_reset: bool = False,
    ):
        """
        Allows bot admins or lead moderators to reset a user's voice channel.
        """
        if not self.is_bot_admin_or_lead_moderator(interaction.user):
            await send_message(
                interaction,
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        jtc_channel_id = jtc_channel.id if jtc_channel else None
        
        # If a specific JTC channel was provided, validate it's a JTC channel
        if jtc_channel:
            join_to_create_channels = self.guild_jtc_channels.get(guild_id, [])
            if not join_to_create_channels:
                # Try legacy fallback
                join_to_create_channels = [int(id) for id in self.join_to_create_channel_ids]
                
            if jtc_channel.id not in join_to_create_channels:
                await send_message(
                    interaction,
                    f"The channel {jtc_channel.mention} is not a join-to-create channel.",
                    ephemeral=True
                )
                return

        # If global_reset requested, reject combination with a specific jtc_channel
        if global_reset and jtc_channel is not None:
            await send_message(
                interaction,
                "Cannot specify a specific JTC channel when performing a global reset. Use either a channel or global_reset.",
                ephemeral=True,
            )
            return

        # If global reset requested, perform across all guilds and channels
        if global_reset:
            await send_message(interaction, "Starting global reset for user...", ephemeral=True)
            await self._reset_all_user_settings(user)
            await send_message(
                interaction, f"All voice channel settings and channels for {user.display_name} have been reset across all guilds.", ephemeral=True
            )
            logger.info(f"{interaction.user.display_name} performed global reset for {user.display_name}.")
            return
        
        # If no JTC channel was specified but user has an active channel, get its JTC channel
        if not jtc_channel_id:
            active_channel = await get_user_channel(self.bot, user, guild_id)
            if active_channel:
                async with Database.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT jtc_channel_id FROM user_voice_channels WHERE voice_channel_id = ? AND guild_id = ?",
                        (active_channel.id, guild_id),
                    )
                    if row := await cursor.fetchone():
                        jtc_channel_id = row[0]
                        
        # Reset settings with guild context
        await self._reset_current_channel_settings(user, guild_id, jtc_channel_id)

        # If user has an active channel, delete it
        active_channel = await get_user_channel(self.bot, user, guild_id, jtc_channel_id)
        if active_channel:
            try:
                await delete_channel(active_channel)
                logger.info(
                    f"Deleted {user.display_name}'s active voice channel as part of admin reset."
                )
            except discord.NotFound:
                logger.warning(
                    f"Channel '{active_channel.id}' not found. It may have already been deleted."
                )

        # Build success message
        if jtc_channel:
            success_message = f"{user.display_name}'s voice channel settings for {jtc_channel.name} have been reset."
        else:
            success_message = f"{user.display_name}'s voice channel settings for this server have been reset."
            
        await send_message(
            interaction,
            success_message,
            ephemeral=True,
        )
        logger.info(
            f"{interaction.user.display_name} reset {user.display_name}'s voice channel settings."
        )

    @app_commands.command(
        name="admin_list",
        description="View saved permissions and settings for a user's voice channel (Admins/Moderators only).",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user whose voice channel settings you want to view."
    )
    async def admin_list_channel(
        self, interaction: discord.Interaction, user: discord.Member
    ):
        """
        Allows an admin to view saved channel settings and permissions for a specific user.
        """
        admin_role_ids = self.bot_admin_role_ids + self.lead_moderator_role_ids
        user_roles = [role.id for role in interaction.user.roles]
        if all(role_id not in user_roles for role_id in admin_role_ids):
            await send_message(
                interaction,
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        # Create a fake interaction for the target user to fetch their settings
        class FakeInteraction:
            def __init__(self, real_interaction, target_user):
                self.user = target_user
                self.guild = real_interaction.guild
                self.response = real_interaction.response
                self.followup = real_interaction.followup

        fake_interaction = FakeInteraction(interaction, user)
        settings = await fetch_channel_settings(self.bot, fake_interaction)

        if not settings:
            await send_message(
                interaction,
                f"{user.display_name} does not have any saved channel settings.",
                ephemeral=True,
            )
            return

        # Determine JTC channel name for display
        jtc_channel_id = settings.get("jtc_channel_id")
        jtc_name = "Unknown JTC"
        if jtc_channel_id:
            jtc_channel = self.bot.get_channel(jtc_channel_id)
            if jtc_channel:
                jtc_name = jtc_channel.name

        formatted = format_channel_settings(settings, fake_interaction)
        if formatted:
            embed = create_voice_settings_embed(
                settings=settings,
                formatted=formatted,
                title=f"Saved Channel Settings for {user.display_name}",
                footer=f"{jtc_name} | Use /voice admin_reset to reset this user's channel.",
            )
            await send_message(interaction, "", embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function to add the VoiceAdminCog."""
    await bot.add_cog(VoiceAdminCog(bot))
    logger.info("Voice admin cog loaded.")
