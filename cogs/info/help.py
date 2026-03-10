"""Help command Cog for TEST Clanker — dynamically shows accessible commands by permission level."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from helpers.permissions_helper import PermissionLevel, get_permission_level
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class BotCommand:
    """Represents a single bot command with metadata."""

    name: str
    description: str
    permission_level: PermissionLevel
    category: str


# All Discord commands organized by category and permission level
ALL_COMMANDS = [
    # Info Commands (Everyone)
    BotCommand(
        name="/about",
        description="Shows information about TEST Clanker and support contact.",
        permission_level=PermissionLevel.USER,
        category="Info",
    ),
    BotCommand(
        name="/privacy",
        description="Shows privacy policy summary and data-rights request steps.",
        permission_level=PermissionLevel.USER,
        category="Info",
    ),
    # Voice Commands - User Level
    BotCommand(
        name="/voice list",
        description="List all custom permissions and settings in your voice channel.",
        permission_level=PermissionLevel.USER,
        category="Voice",
    ),
    BotCommand(
        name="/voice claim",
        description="Claim ownership of the voice channel if the owner is absent.",
        permission_level=PermissionLevel.USER,
        category="Voice",
    ),
    BotCommand(
        name="/voice transfer <user>",
        description="Transfer your voice channel ownership to another user.",
        permission_level=PermissionLevel.USER,
        category="Voice",
    ),
    BotCommand(
        name="/voice help",
        description="Show help for voice commands.",
        permission_level=PermissionLevel.USER,
        category="Voice",
    ),
    BotCommand(
        name="/voice owner",
        description="List all voice channels managed by the bot and their owners.",
        permission_level=PermissionLevel.USER,
        category="Voice",
    ),
    # Voice Commands - Admin Level
    BotCommand(
        name="/voice setup <category> [num_channels]",
        description="Set up the Join-to-Create voice system.",
        permission_level=PermissionLevel.MODERATOR,
        category="Voice",
    ),
    BotCommand(
        name="/voice add <category> [channel_name]",
        description="Add a new Join-to-Create channel.",
        permission_level=PermissionLevel.MODERATOR,
        category="Voice",
    ),
    BotCommand(
        name="/voice admin_list <user>",
        description="View saved permissions and settings for a user's voice channel.",
        permission_level=PermissionLevel.MODERATOR,
        category="Voice",
    ),
    BotCommand(
        name="/voice admin reset <scope> [member] [confirm]",
        description="Reset voice data for a user or entire guild.",
        permission_level=PermissionLevel.MODERATOR,
        category="Voice",
    ),
    # Info Commands - Staff+
    BotCommand(
        name="/dashboard",
        description="Get a link to the Web Admin Dashboard.",
        permission_level=PermissionLevel.STAFF,
        category="Info",
    ),
    # Verification & Check Commands - Moderator+
    BotCommand(
        name="/check user <member>",
        description="Show verification details for a member.",
        permission_level=PermissionLevel.MODERATOR,
        category="Verification",
    ),
    BotCommand(
        name="/reset-user <member>",
        description="Reset verification timer for a specific member.",
        permission_level=PermissionLevel.MODERATOR,
        category="Verification",
    ),
    BotCommand(
        name="/verify check-user <member>",
        description="Check single user's verification status and org membership.",
        permission_level=PermissionLevel.MODERATOR,
        category="Verification",
    ),
    BotCommand(
        name="/verify check-members <members>",
        description="Check multiple users' verification status and org membership.",
        permission_level=PermissionLevel.MODERATOR,
        category="Verification",
    ),
    BotCommand(
        name="/verify check-channel <channel>",
        description="Check verification for all users in a voice channel.",
        permission_level=PermissionLevel.MODERATOR,
        category="Verification",
    ),
    BotCommand(
        name="/verify check-voice",
        description="Check verification for all users in active voice channels.",
        permission_level=PermissionLevel.MODERATOR,
        category="Verification",
    ),
    # Tickets Commands - Staff+
    BotCommand(
        name="/tickets stats",
        description="Show ticket statistics for this server.",
        permission_level=PermissionLevel.STAFF,
        category="Tickets",
    ),
    BotCommand(
        name="/tickets health",
        description="Show thread health and cleanup candidates.",
        permission_level=PermissionLevel.STAFF,
        category="Tickets",
    ),
    # Admin Commands - Bot Admin+
    BotCommand(
        name="/reset-all",
        description="Reset verification timers for **all members**.",
        permission_level=PermissionLevel.BOT_ADMIN,
        category="Admin",
    ),
    BotCommand(
        name="/flush-announcements",
        description="Force flush announcement queue immediately.",
        permission_level=PermissionLevel.BOT_ADMIN,
        category="Admin",
    ),
    BotCommand(
        name="/status [detailed]",
        description="Show detailed bot health and status information.",
        permission_level=PermissionLevel.BOT_ADMIN,
        category="Admin",
    ),
    BotCommand(
        name="/tickets cleanup [older_than] [dry_run]",
        description="Delete old closed ticket threads to free up space.",
        permission_level=PermissionLevel.BOT_ADMIN,
        category="Tickets",
    ),
    # Role Delegation - Custom Permission
    BotCommand(
        name="/role-grant <member> <role>",
        description="Grant a role under delegation policy (if you have permission).",
        permission_level=PermissionLevel.MODERATOR,
        category="Role Delegation",
    ),
    BotCommand(
        name="/role-revoke <member> <role>",
        description="Revoke a role under delegation policy (if you have permission).",
        permission_level=PermissionLevel.MODERATOR,
        category="Role Delegation",
    ),
]


def get_accessible_commands(
    permission_level: PermissionLevel,
) -> dict[str, list[BotCommand]]:
    """
    Filter all commands by permission level, organized by category.

    Args:
        permission_level: User's permission level (hierarchy-aware)

    Returns:
        Dict mapping category name to list of accessible commands
    """
    accessible: dict[str, list[BotCommand]] = {}

    for cmd in ALL_COMMANDS:
        # Include command if user's level >= command's required level
        if permission_level.value >= cmd.permission_level.value:
            if cmd.category not in accessible:
                accessible[cmd.category] = []
            accessible[cmd.category].append(cmd)

    return accessible


def build_help_embeds(
    commands_by_category: dict[str, list[BotCommand]],
    permission_level: PermissionLevel,
) -> list[discord.Embed]:
    """
    Build help embeds organized by category.

    Args:
        commands_by_category: Dict of category -> commands
        permission_level: User's permission level (for footer)

    Returns:
        List of Discord embeds
    """
    embeds: list[discord.Embed] = []

    # Summary embed
    total_commands = sum(len(cmds) for cmds in commands_by_category.values())
    summary_embed = discord.Embed(
        title="📋 TEST Clanker Command Help",
        description=f"Showing **{total_commands}** commands available at your level.",
        color=0x3498DB,
    )
    summary_embed.add_field(
        name="Your Permission Level",
        value=f"**{permission_level.name}**",
        inline=False,
    )
    summary_embed.add_field(
        name="Categories",
        value=", ".join(sorted(commands_by_category.keys())),
        inline=False,
    )
    summary_embed.set_footer(text="Use the category embeds below for full details.")
    embeds.append(summary_embed)

    # Category embeds - sorted for consistency
    for category in sorted(commands_by_category.keys()):
        commands = commands_by_category[category]

        embed = discord.Embed(
            title=f"📚 {category}",
            color=0x3498DB,
            description=f"{len(commands)} command(s) in this category",
        )

        for cmd in commands:
            embed.add_field(
                name=cmd.name,
                value=cmd.description,
                inline=False,
            )

        embed.set_footer(text=f"Permission Level: {permission_level.name}")
        embeds.append(embed)

    return embeds


class HelpCog(commands.Cog):
    """Expose the /help slash command with contextual permission-based filtering."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="help",
        description="Show commands available to your permission level.",
    )
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction) -> None:
        """
        Send help embeds showing only commands the user has permission to access.

        The help message is ephemeral (visible only to the user) and organized by
        command category. Permission level is determined by the user's configured roles.
        """
        try:
            if (
                not isinstance(interaction.user, discord.Member)
                or interaction.guild is None
            ):
                await interaction.response.send_message(
                    "❌ This command must be used in a server.",
                    ephemeral=True,
                )
                return

            # Defer before async operations
            await interaction.response.defer(ephemeral=True)

            # Get user's permission level
            user_level = await get_permission_level(
                self.bot, interaction.user, interaction.guild
            )

            # Get accessible commands for this user
            accessible = get_accessible_commands(user_level)

            # Build embeds
            embeds = build_help_embeds(accessible, user_level)

            # Send ephemeral response
            await interaction.followup.send(embeds=embeds, ephemeral=True)

            logger.debug(
                "Help command executed: user_id=%s level=%s commands=%d",
                interaction.user.id,
                user_level.name,
                sum(len(cmds) for cmds in accessible.values()),
            )

        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("Failed to send /help embeds", exc_info=exc)

            message = "❌ Unable to show help right now. Please try again later."
            if interaction.response.is_done():
                with contextlib.suppress(Exception):
                    await interaction.followup.send(message, ephemeral=True)
            else:
                with contextlib.suppress(Exception):
                    await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Register the Help cog."""
    await bot.add_cog(HelpCog(bot))
