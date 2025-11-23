"""
Voice Commands Cog

Handles all voice-related slash commands and user interactions.
All business logic is delegated to the VoiceService.
"""

import builtins
import contextlib
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from helpers.decorators import require_admin
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
        if not hasattr(self.bot, "services") or self.bot.services is None:
            raise RuntimeError("Bot services not initialized")
        return self.bot.services.voice

    @app_commands.command(
        name="list",
        description="List all custom permissions and settings in your voice channel",
    )
    async def list_permissions(self, interaction: discord.Interaction) -> None:
        """List all custom permissions and settings for user's voice channel."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Use the new helper to fetch settings
            from helpers.voice_settings import fetch_channel_settings

            result = await fetch_channel_settings(
                bot=self.bot,
                interaction=interaction,
                target_user=None,  # Use interaction user
                allow_inactive=True,
            )

            if not result["settings"] and not result["embeds"]:
                if result["is_active"]:
                    await interaction.followup.send(
                        "❌ You're in a voice channel, but it's not managed by the bot or has no saved settings.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "❌ You don't have an active voice channel or saved settings. Join a voice channel or configure settings first.",
                        ephemeral=True,
                    )
                return

            # Send the appropriate embed
            if result["embeds"]:
                embed = result["embeds"][
                    0
                ]  # Use the first (and usually only) embed for user list
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # Fallback if no embeds but we have settings
                embed = discord.Embed(
                    title="🎙️ Your Voice Channel Settings", color=discord.Color.blue()
                )
                embed.add_field(
                    name="Settings Found",
                    value="You have saved settings, but they could not be displayed properly.",
                    inline=False,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception("Error in list_permissions command", exc_info=e)
            from helpers.discord_reply import send_user_error
            from helpers.error_messages import format_user_error
            with contextlib.suppress(builtins.BaseException):
                await send_user_error(
                    interaction, format_user_error("UNKNOWN")
                )

    @app_commands.command(
        name="claim",
        description="Claim ownership of the voice channel if the owner is absent",
    )
    async def claim_channel(self, interaction: discord.Interaction) -> None:
        """Claim ownership of voice channel if current owner is absent."""
        from helpers.discord_reply import send_user_error, send_user_success
        from helpers.error_messages import format_user_error

        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.claim_voice_channel(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                user=interaction.user,
            )

            if result.success:
                # Format success message
                message = f"✅ **Channel claimed**\nYou now own {result.channel_mention}."
                await send_user_success(interaction, message)
            else:
                # Format error with metadata if available
                kwargs = result.metadata or {}
                error_msg = format_user_error(result.error, **kwargs)
                await send_user_error(interaction, error_msg)

        except Exception as e:
            logger.exception("Error in claim_channel command", exc_info=e)
            with contextlib.suppress(builtins.BaseException):
                from helpers.error_messages import format_user_error
                await send_user_error(
                    interaction, format_user_error("UNKNOWN")
                )

    @app_commands.command(
        name="transfer", description="Transfer channel ownership to another user"
    )
    @app_commands.describe(new_owner="Who should be the new channel owner?")
    async def transfer_ownership(
        self, interaction: discord.Interaction, new_owner: discord.Member
    ) -> None:
        """Transfer channel ownership to another user."""
        from helpers.discord_reply import send_user_error, send_user_success
        from helpers.error_messages import format_user_error, format_user_success

        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.transfer_voice_channel_ownership(
                guild_id=interaction.guild_id,
                current_owner_id=interaction.user.id,
                new_owner_id=new_owner.id,
                new_owner=new_owner,
            )

            if result.success:
                # Format success message
                message = format_user_success(
                    "TRANSFERRED",
                    user_mention=new_owner.mention,
                    channel_mention=result.channel_mention,
                )
                await send_user_success(interaction, message)
            else:
                # Format error
                kwargs = result.metadata or {}
                error_msg = format_user_error(result.error, **kwargs)
                await send_user_error(interaction, error_msg)

        except Exception as e:
            logger.exception("Error in transfer_ownership command", exc_info=e)
            with contextlib.suppress(builtins.BaseException):
                await send_user_error(
                    interaction, format_user_error("UNKNOWN")
                )

    @app_commands.command(name="help", description="Show help for voice commands")
    async def voice_help(self, interaction: discord.Interaction) -> None:
        """Show help information for voice commands."""
        embed = discord.Embed(
            title="🎙️ Voice Channel Commands",
            description="Commands for managing your dynamic voice channels",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="/voice list",
            value="List all custom permissions and settings in your voice channel",
            inline=False,
        )

        embed.add_field(
            name="/voice claim",
            value="Claim ownership of a voice channel if the current owner is absent",
            inline=False,
        )

        embed.add_field(
            name="/voice transfer <user>",
            value="Transfer ownership of your voice channel to another user",
            inline=False,
        )

        embed.add_field(
            name="/voice owner",
            value="List all voice channels and their owners",
            inline=False,
        )

        embed.add_field(
            name="/voice setup",
            value="Set up the voice channel system (Admin only)",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="owner",
        description="List all voice channels managed by the bot and their owners",
    )
    async def list_owners(self, interaction: discord.Interaction) -> None:
        """List all voice channels and their owners."""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get all voice channels from service
            channels = await self.voice_service.get_all_voice_channels(
                interaction.guild_id
            )

            if not channels:
                await interaction.followup.send(
                    "📭 No managed voice channels found.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🎙️ Managed Voice Channels",
                description=f"All voice channels managed by the bot in **{interaction.guild.name}**",
                color=discord.Color.blue(),
            )

            channel_list = []
            for channel_info in channels:
                channel = interaction.guild.get_channel(
                    channel_info["voice_channel_id"]
                )
                owner = interaction.guild.get_member(channel_info["owner_id"])

                if channel and owner:
                    member_count = len(channel.members)
                    channel_list.append(
                        f"**{channel.name}** - {owner.mention} ({member_count} members)"
                    )
                elif channel:
                    channel_list.append(
                        f"**{channel.name}** - Unknown owner ({len(channel.members)} members)"
                    )

            if channel_list:
                # Split into chunks if too long
                chunks = [
                    channel_list[i : i + 10] for i in range(0, len(channel_list), 10)
                ]
                for i, chunk in enumerate(chunks):
                    field_name = (
                        "📋 Voice Channels"
                        if i == 0
                        else f"📋 Voice Channels (continued {i + 1})"
                    )
                    embed.add_field(
                        name=field_name, value="\n".join(chunk), inline=False
                    )

            embed.set_footer(text=f"Total: {len(channels)} channels")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception("Error in list_owners command", exc_info=e)
            from helpers.discord_reply import send_user_error
            from helpers.error_messages import format_user_error
            with contextlib.suppress(builtins.BaseException):
                await send_user_error(
                    interaction, format_user_error("UNKNOWN")
                )

    @app_commands.command(name="setup", description="Set up the voice channel system")
    @app_commands.describe(
        category="Category to place voice channels in",
        num_channels="Number of 'Join to Create' channels",
    )
    @require_admin()
    async def setup_voice_system(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        num_channels: int = 1,
    ) -> None:
        """Set up the voice channel system (Admin only)."""
        from helpers.discord_reply import send_user_error, send_user_success
        from helpers.error_messages import format_user_error

        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Delegate to voice service
            result = await self.voice_service.setup_voice_system(
                guild_id=interaction.guild_id,
                category=category,
                num_channels=num_channels,
            )

            if result.success:
                # Build success message
                message = f"✅ **Setup complete**\nCreated {num_channels} Join-to-Create channel{'s' if num_channels > 1 else ''} in {category.name}."
                await send_user_success(interaction, message)
            else:
                # Format error
                kwargs = result.metadata or {}
                error_msg = format_user_error(result.error, **kwargs)
                await send_user_error(interaction, error_msg)

        except Exception as e:
            logger.exception("Error in setup_voice_system command", exc_info=e)
            with contextlib.suppress(builtins.BaseException):
                await send_user_error(
                    interaction, format_user_error("UNKNOWN")
                )

    @app_commands.command(
        name="admin_list",
        description="View saved permissions and settings for a user's voice channel",
    )
    @app_commands.describe(
        user="The user whose voice channel settings you want to view"
    )
    @require_admin()
    async def admin_list(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        """View saved permissions and settings for a user's voice channel (Admin only)."""
        from helpers.error_messages import format_user_error

        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Use the new helper to fetch settings
            from helpers.voice_settings import fetch_channel_settings

            result = await fetch_channel_settings(
                bot=self.bot,
                interaction=interaction,
                target_user=user,
                allow_inactive=True,
            )

            if not result["settings"] and not result["embeds"]:
                await interaction.followup.send(
                    f"📭 No saved voice channel settings found for {user.mention}.",
                    ephemeral=True,
                )
                return

            # Send all embeds (one per JTC channel with settings)
            if result["embeds"]:
                for embed in result["embeds"]:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # Fallback if no embeds but we have settings
                embed = discord.Embed(
                    title=f"🔧 Voice Settings for {user.display_name}",
                    description=f"Administrative view of voice channel settings for {user.mention}",
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="Settings Found",
                    value="Settings exist but could not be formatted properly.",
                    inline=False,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception("Error in admin_list command", exc_info=e)
            from helpers.discord_reply import send_user_error
            from helpers.error_messages import format_user_error
            with contextlib.suppress(builtins.BaseException):
                await send_user_error(
                    interaction, format_user_error("UNKNOWN")
                )


class AdminCommands(app_commands.Group):
    """Admin-only voice commands."""

    def __init__(self, voice_cog: VoiceCommands):
        super().__init__(name="admin", description="Admin voice management commands")
        self.voice_cog = voice_cog

    @property
    def voice_service(self):
        """Get the voice service from the parent cog."""
        return self.voice_cog.voice_service

    @property
    def bot(self):
        """Get the bot from the parent cog."""
        return self.voice_cog.bot

    @app_commands.command(
        name="reset",
        description="Reset voice data for a user or entire guild (Admin only)",
    )
    @app_commands.describe(
        scope="Choose 'user' to reset a specific user's data, or 'all' to reset all guild data",
        member="The member to reset (required when scope is 'user')",
        confirm="REQUIRED for 'all' scope - type YES to confirm destructive operation",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="user", value="user"),
            app_commands.Choice(name="all", value="all"),
        ]
    )
    @require_admin()
    async def admin_reset(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
        member: discord.Member = None,
        confirm: str | None = None,
    ) -> None:
        """Admin command to reset voice data for a user or entire guild."""
        from helpers.error_messages import format_user_error

        # Validate parameters
        if scope.value == "user" and member is None:
            await interaction.response.send_message(
                "❌ You must specify a member when using 'user' scope.", ephemeral=True
            )
            return

        if scope.value == "all" and member is not None:
            await interaction.response.send_message(
                "❌ Cannot specify a member when using 'all' scope.", ephemeral=True
            )
            return

        # Require explicit confirmation for destructive "all" operation
        if scope.value == "all" and (not confirm or confirm.upper() != "YES"):
            embed = discord.Embed(
                title="⚠️ Confirmation Required",
                description=(
                    "**DESTRUCTIVE OPERATION WARNING**\n\n"
                    "This will **permanently delete ALL voice data** for the entire guild:\n"
                    "• All user voice channel ownerships\n"
                    "• All voice channel permissions\n"
                    "• All voice settings and configurations\n"
                    "• All voice channel history\n"
                    "• All JTC (Join-to-Create) configurations\n\n"
                    "**To confirm this destructive operation:**\n"
                    "Re-run this command with `confirm: YES` (exactly as shown)\n\n"
                    "⚠️ **This action cannot be undone!**"
                ),
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="🔄 Correct Usage",
                value="`/voice admin reset scope:all confirm:YES`",
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild_id

            if scope.value == "user":
                # Reset specific user
                await self._reset_user_data(interaction, guild_id, member)
            else:
                # Reset all guild data
                await self._reset_all_guild_data(interaction, guild_id)

        except Exception as e:
            logger.exception("Error in admin_reset command", exc_info=e)
            from helpers.error_messages import format_user_error
            await interaction.followup.send(
                format_user_error("UNKNOWN"),
                ephemeral=True,
            )

    async def _reset_user_data(
        self, interaction: discord.Interaction, guild_id: int, member: discord.Member
    ) -> None:
        """Reset data for a specific user."""

        logger.info(
            f"Admin {interaction.user} ({interaction.user.id}) resetting voice data for user {member} ({member.id}) in guild {guild_id}"
        )

        # Delete user's managed channel if it exists
        channel_result = await self.voice_service.delete_user_owned_channel(
            guild_id, member.id
        )

        # Purge all voice-related database records for this user with cache cleanup
        deleted_counts = await self.voice_service.purge_voice_data_with_cache_clear(
            guild_id, member.id
        )

        # Create summary
        total_rows = sum(deleted_counts.values())
        channel_msg = ""
        if channel_result["channel_deleted"]:
            channel_msg = (
                f"\n🗑️ Deleted voice channel (ID: {channel_result['channel_id']})"
            )
        elif channel_result["channel_id"]:
            channel_msg = f"\n⚠️ Channel {channel_result['channel_id']} could not be deleted (may already be gone)"

        # Log the action with comprehensive details
        logger.info(
            f"User reset complete - Admin: {interaction.user.display_name} ({interaction.user.id}), "
            f"Target: {member.display_name} ({member.id}), Guild: {guild_id}, "
            f"Total rows deleted: {total_rows}, Channel deleted: {channel_result['channel_deleted']}"
        )

        # Log detailed breakdown for administrative tracking
        for table, count in deleted_counts.items():
            if count > 0:
                logger.info(
                    f"User reset - {table}: {count} records deleted for user {member.id}"
                )

        if channel_result["channel_deleted"]:
            logger.info(
                f"User reset - voice channel {channel_result['channel_id']} successfully deleted"
            )
        elif channel_result["channel_id"]:
            logger.warning(
                f"User reset - voice channel {channel_result['channel_id']} deletion failed"
            )

        embed = discord.Embed(
            title="✅ User Voice Data Reset Complete",
            description=f"Successfully reset voice data for {member.mention}",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="📊 Database Records Deleted",
            value=f"**Total:** {total_rows} rows\n"
            + "\n".join(
                f"**{table}:** {count}"
                for table, count in deleted_counts.items()
                if count > 0
            ),
            inline=False,
        )

        if channel_msg:
            embed.add_field(name="🎤 Channel Action", value=channel_msg, inline=False)

        embed.set_footer(text=f"Reset by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _reset_all_guild_data(
        self, interaction: discord.Interaction, guild_id: int
    ) -> None:
        """Reset all voice data for the guild."""

        logger.info(
            f"Admin {interaction.user} ({interaction.user.id}) resetting ALL voice data for guild {guild_id}"
        )

        # Get all managed channels for this guild before deletion
        managed_channels = await self.voice_service.get_all_guild_managed_channels(
            guild_id
        )

        # Delete all managed channels
        deleted_channels = []
        failed_channels = []

        for channel_id in managed_channels:
            if self.bot:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(
                            reason=f"Admin guild-wide voice reset by {interaction.user}"
                        )
                        deleted_channels.append(channel_id)
                        logger.info(
                            f"Deleted voice channel {channel_id} during guild reset"
                        )
                    except (discord.NotFound, discord.Forbidden) as e:
                        failed_channels.append(channel_id)
                        logger.warning(f"Could not delete channel {channel_id}: {e}")
                else:
                    failed_channels.append(channel_id)

        # Clear managed channels cache for this guild
        if managed_channels:
            # Remove all guild channels from the managed set
            for channel_id in managed_channels:
                self.voice_service.managed_voice_channels.discard(channel_id)

        # Purge all voice-related database records for this guild with cache cleanup
        deleted_counts = await self.voice_service.purge_voice_data_with_cache_clear(
            guild_id
        )

        # Create summary
        total_rows = sum(deleted_counts.values())

        # Log the action with comprehensive details
        logger.info(
            f"Guild reset complete - Admin: {interaction.user.display_name} ({interaction.user.id}), "
            f"Guild: {interaction.guild.name} ({guild_id}), Total rows deleted: {total_rows}, "
            f"Channels deleted: {len(deleted_channels)}, Channels failed: {len(failed_channels)}"
        )

        # Log detailed breakdown for administrative tracking
        for table, count in deleted_counts.items():
            if count > 0:
                logger.info(
                    f"Guild reset - {table}: {count} records deleted for guild {guild_id}"
                )

        # Log channel deletion details
        if deleted_channels:
            logger.info(
                f"Guild reset - Successfully deleted channels: {deleted_channels}"
            )
        if failed_channels:
            logger.warning(
                f"Guild reset - Failed to delete channels: {failed_channels}"
            )

        # Log major administrative action
        logger.warning(
            f"MAJOR ADMIN ACTION: Complete guild voice reset performed by "
            f"{interaction.user.display_name} ({interaction.user.id}) on guild "
            f"{interaction.guild.name} ({guild_id}). All voice data wiped."
        )

        embed = discord.Embed(
            title="✅ Guild Voice Data Reset Complete",
            description="Successfully reset ALL voice data for this server",
            color=discord.Color.red(),  # Red to indicate this was a major action
        )

        embed.add_field(
            name="📊 Database Records Deleted",
            value=f"**Total:** {total_rows} rows\n"
            + "\n".join(
                f"**{table}:** {count}"
                for table, count in deleted_counts.items()
                if count > 0
            ),
            inline=False,
        )

        channel_summary = []
        if deleted_channels:
            channel_summary.append(f"✅ **Deleted:** {len(deleted_channels)} channels")
        if failed_channels:
            channel_summary.append(
                f"⚠️ **Failed/Missing:** {len(failed_channels)} channels"
            )

        if channel_summary:
            embed.add_field(
                name="🎤 Channel Actions",
                value="\n".join(channel_summary),
                inline=False,
            )

        embed.add_field(
            name="⚠️ Warning",
            value="This action reset ALL voice data for the entire server. All users will need to recreate their settings.",
            inline=False,
        )

        embed.set_footer(text=f"Reset by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Set up the Voice Commands cog."""
    voice_cog = VoiceCommands(bot)

    # Add the admin subgroup to the main voice group
    voice_cog.app_command.add_command(AdminCommands(voice_cog))

    await bot.add_cog(voice_cog)
