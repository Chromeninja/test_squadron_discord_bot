"""
Voice Commands Cog

Handles all voice-related slash commands and user interactions.
All business logic is delegated to the VoiceService.
"""

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from utils.logging import get_logger

if TYPE_CHECKING:
    from services.service_container import ServiceContainer

logger = get_logger(__name__)


class VoiceCommands(commands.GroupCog, name="voice"):
    """Voice channel management commands."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.services: ServiceContainer | None = None

    @property
    def voice_service(self):
        """Get the voice service from the bot's service container."""
        if not hasattr(self.bot, 'services') or self.bot.services is None:
            raise RuntimeError("Bot services not initialized")
        return self.bot.services.voice

    @app_commands.command(name="settings", description="Manage your voice channel settings")
    async def voice_settings(self, interaction: discord.Interaction) -> None:
        """Open voice channel settings interface."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get user's voice channel info from service
            channel_info = await self.voice_service.get_user_voice_channel_info(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id
            )

            if not channel_info:
                await interaction.followup.send(
                    "❌ You don't have an active voice channel. Use `/voice create` to create one.",
                    ephemeral=True
                )
                return

            # Create and send settings view
            settings_embed = await self.voice_service.create_settings_embed(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id
            )

            view = await self.voice_service.create_settings_view(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id
            )

            await interaction.followup.send(
                embed=settings_embed,
                view=view,
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in voice_settings command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while loading voice settings.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="cleanup", description="Clean up inactive voice channels")
    @app_commands.describe(force="Force cleanup of all channels regardless of activity")
    async def cleanup_channels(
        self,
        interaction: discord.Interaction,
        force: bool = False
    ) -> None:
        """Clean up inactive voice channels (Admin only)."""
        # Check permissions
        admin_role_ids = await self.voice_service.get_admin_role_ids()
        if not any(role.id in admin_role_ids for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            cleanup_result = await self.voice_service.cleanup_inactive_channels(
                guild_id=interaction.guild_id,
                force=force
            )

            await interaction.followup.send(
                f"🧹 Cleanup completed. Removed {cleanup_result.deleted_count} inactive channels.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in cleanup_channels command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred during cleanup.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="list", description="List all custom permissions and settings in your voice channel")
    async def list_permissions(self, interaction: discord.Interaction) -> None:
        """List all custom permissions and settings for user's voice channel."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get user's voice channel settings from service
            settings = await self.voice_service.get_user_channel_settings(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id
            )

            if not settings:
                await interaction.followup.send(
                    "❌ You don't have an active voice channel with saved settings.",
                    ephemeral=True
                )
                return

            # Create settings embed
            embed = await self.voice_service.create_settings_list_embed(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                settings=settings
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in list_permissions command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while retrieving channel settings.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="claim", description="Claim ownership of the voice channel if the owner is absent")
    async def claim_channel(self, interaction: discord.Interaction) -> None:
        """Claim ownership of voice channel if current owner is absent."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.claim_voice_channel(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                user=interaction.user
            )

            if result.success:
                await interaction.followup.send(
                    f"✅ Successfully claimed ownership of voice channel: {result.channel_mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {result.error}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in claim_channel command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while claiming the channel.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="transfer", description="Transfer channel ownership to another user")
    @app_commands.describe(new_owner="Who should be the new channel owner?")
    async def transfer_ownership(
        self,
        interaction: discord.Interaction,
        new_owner: discord.Member
    ) -> None:
        """Transfer channel ownership to another user."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.transfer_voice_channel_ownership(
                guild_id=interaction.guild_id,
                current_owner_id=interaction.user.id,
                new_owner_id=new_owner.id,
                new_owner=new_owner
            )

            if result.success:
                await interaction.followup.send(
                    f"✅ Successfully transferred ownership of voice channel to {new_owner.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {result.error}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in transfer_ownership command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while transferring ownership.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="help", description="Show help for voice commands")
    async def voice_help(self, interaction: discord.Interaction) -> None:
        """Show help information for voice commands."""
        embed = discord.Embed(
            title="🎙️ Voice Channel Commands",
            description="Commands for managing your dynamic voice channels",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="/voice settings",
            value="Open the settings interface for your voice channel",
            inline=False
        )

        embed.add_field(
            name="/voice list",
            value="List all custom permissions and settings in your voice channel",
            inline=False
        )

        embed.add_field(
            name="/voice claim",
            value="Claim ownership of a voice channel if the current owner is absent",
            inline=False
        )

        embed.add_field(
            name="/voice transfer <user>",
            value="Transfer ownership of your voice channel to another user",
            inline=False
        )

        embed.add_field(
            name="/voice owner",
            value="List all voice channels and their owners (Admin only)",
            inline=False
        )

        embed.add_field(
            name="/voice setup",
            value="Set up the voice channel system (Admin only)",
            inline=False
        )

        embed.add_field(
            name="/voice cleanup",
            value="Clean up inactive voice channels (Admin only)",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="owner", description="List all voice channels managed by the bot and their owners")
    async def list_owners(self, interaction: discord.Interaction) -> None:
        """List all voice channels and their owners (Admin only)."""
        # Check permissions
        admin_role_ids = await self.voice_service.get_admin_role_ids()
        if not any(role.id in admin_role_ids for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Get all voice channels from service
            channels = await self.voice_service.get_all_voice_channels(interaction.guild_id)

            if not channels:
                await interaction.followup.send(
                    "📭 No managed voice channels found.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🎙️ Managed Voice Channels",
                description=f"All voice channels managed by the bot in **{interaction.guild.name}**",
                color=discord.Color.blue()
            )

            channel_list = []
            for channel_info in channels:
                channel = interaction.guild.get_channel(channel_info['voice_channel_id'])
                owner = interaction.guild.get_member(channel_info['owner_id'])

                if channel and owner:
                    member_count = len(channel.members)
                    channel_list.append(f"**{channel.name}** - {owner.mention} ({member_count} members)")
                elif channel:
                    channel_list.append(f"**{channel.name}** - Unknown owner ({len(channel.members)} members)")

            if channel_list:
                # Split into chunks if too long
                chunks = [channel_list[i:i+10] for i in range(0, len(channel_list), 10)]
                for i, chunk in enumerate(chunks):
                    field_name = "📋 Voice Channels" if i == 0 else f"📋 Voice Channels (continued {i+1})"
                    embed.add_field(
                        name=field_name,
                        value="\n".join(chunk),
                        inline=False
                    )

            embed.set_footer(text=f"Total: {len(channels)} channels")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in list_owners command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while retrieving channel information.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="setup", description="Set up the voice channel system")
    @app_commands.describe(
        category="Category to place voice channels in",
        num_channels="Number of 'Join to Create' channels"
    )
    async def setup_voice_system(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        num_channels: int = 1
    ) -> None:
        """Set up the voice channel system (Admin only)."""
        # Check permissions
        admin_role_ids = await self.voice_service.get_admin_role_ids()
        if not any(role.id in admin_role_ids for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.setup_voice_system(
                guild_id=interaction.guild_id,
                category=category,
                num_channels=num_channels
            )

            if result.success:
                await interaction.followup.send(
                    f"✅ Voice system setup complete! Created {num_channels} Join-to-Create channels in {category.name}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Setup failed: {result.error}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in setup_voice_system command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred during voice system setup.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="admin_reset", description="Admin command to reset a user's voice channel")
    @app_commands.describe(
        user="The user whose voice channel settings you want to reset",
        jtc_channel="Specific join-to-create channel to reset settings for (optional)",
        global_reset="If true, reset this user's settings across all guilds and channels"
    )
    async def admin_reset(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        jtc_channel: discord.VoiceChannel | None = None,
        global_reset: bool = False
    ) -> None:
        """Admin command to reset a user's voice channel settings."""
        # Check permissions
        admin_role_ids = await self.voice_service.get_admin_role_ids()
        if not any(role.id in admin_role_ids for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.admin_reset_user_settings(
                guild_id=interaction.guild_id,
                user_id=user.id,
                jtc_channel_id=jtc_channel.id if jtc_channel else None,
                global_reset=global_reset
            )

            if result.success:
                reset_scope = "globally" if global_reset else f"in {interaction.guild.name}"
                channel_scope = f" for {jtc_channel.name}" if jtc_channel else ""
                await interaction.followup.send(
                    f"✅ Reset voice settings for {user.mention} {reset_scope}{channel_scope}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Reset failed: {result.error}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in admin_reset command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred during reset.",
                    ephemeral=True
                )
            except:
                pass

    @app_commands.command(name="admin_list", description="View saved permissions and settings for a user's voice channel")
    @app_commands.describe(user="The user whose voice channel settings you want to view")
    async def admin_list(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ) -> None:
        """View saved permissions and settings for a user's voice channel (Admin only)."""
        # Check permissions
        admin_role_ids = await self.voice_service.get_admin_role_ids()
        if not any(role.id in admin_role_ids for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Get user's settings from service
            settings = await self.voice_service.get_user_channel_settings(
                guild_id=interaction.guild_id,
                user_id=user.id
            )

            if not settings:
                await interaction.followup.send(
                    f"📭 No saved voice channel settings found for {user.mention}.",
                    ephemeral=True
                )
                return

            # Create admin settings embed
            embed = await self.voice_service.create_admin_settings_embed(
                guild_id=interaction.guild_id,
                user_id=user.id,
                user=user,
                settings=settings
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in admin_list command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while retrieving user settings.",
                    ephemeral=True
                )
            except:
                pass


async def setup(bot: commands.Bot) -> None:
    """Set up the Voice Commands cog."""
    await bot.add_cog(VoiceCommands(bot))
