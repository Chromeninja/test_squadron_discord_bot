"""
Embed Helper Module

Provides utility functions for creating and formatting Discord embeds with
consistent styling and branding for the TEST Clanker Discord bot.
"""

from typing import TYPE_CHECKING

import discord  # type: ignore[import-not-found]

from helpers.constants import DEFAULT_ORG_SID
from helpers.permissions_helper import get_role_display_name
from utils.about_metadata import (
    BOT_DESCRIPTION,
    BOT_NAME,
    BOT_PURPOSE_ITEMS,
    BOT_VERSION,
    PRIVACY_POLICY_URL,
    PRIVACY_SUMMARY,
    SUPPORT_EMAIL,
    SUPPORT_TICKET_INFO,
    USER_RIGHTS_SUMMARY,
)
from utils.logging import get_logger

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot

# Initialize logger
logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Standard Colors
# -----------------------------------------------------------------------------

class EmbedColors:
    """Standard color constants for Discord embeds."""

    SUCCESS = 0x00FF00  # Green - positive outcomes
    ERROR = 0xFF0000  # Red - errors, failures
    WARNING = 0xFFA500  # Orange - warnings, cooldowns
    INFO = 0x3498DB  # Blue - informational
    PRIMARY = 0xFFBB00  # Yellow - TEST Squadron branding
    NEUTRAL = 0x95A5A6  # Gray - neutral status
    VOICE_ACTIVE = 0x00FF00  # Green - active voice channel
    VOICE_SAVED = 0x3498DB  # Blue - saved settings
    VERIFICATION = 0xFFBB00  # Yellow - verification embeds
    ADMIN = 0xE74C3C  # Red-ish - admin actions


# Standard thumbnail URL - set to None for org-agnostic deployments
# Individual guilds can configure organization.logo_url
DEFAULT_THUMBNAIL: str | None = None


def create_embed(
    title: str,
    description: str,
    color: int = 0x00FF00,
    thumbnail_url: str | None = None,
) -> discord.Embed:
    """
    Creates a Discord embed with the given parameters.

    Args:
        title (str): The title of the embed.
        description (str): The description/content of the embed.
        color (int, optional): The color of the embed in hexadecimal. Defaults to green.
        thumbnail_url (str, optional): URL of the thumbnail image. Defaults to TEST Squadron logo.

    Returns:
        discord.Embed: The created embed object.
    """
    embed = discord.Embed(title=title, description=description, color=color)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed


def create_verification_embed(thumbnail_url: str | None = None) -> discord.Embed:
    """
    Creates the initial verification embed.

    Args:
        thumbnail_url: Optional organization logo URL to display as thumbnail

    Returns:
        discord.Embed: The verification embed.
    """
    title = "📡 Account Verification"
    description = (
        "Welcome! To get started, please **click the 'Get Token' button below**.\n\n"
        "After obtaining your token, verify your RSI / Star Citizen account by using the provided buttons.\n\n"
        "If you don't have an RSI account, you can [sign-up here]"
        "(https://robertsspaceindustries.com/enlist?referral=STAR-MXL7-VM6G)"
    )
    color = 0xFFBB00  # Yellow
    # Use provided thumbnail or fall back to DEFAULT_THUMBNAIL
    return create_embed(title, description, color, thumbnail_url or DEFAULT_THUMBNAIL)


def build_about_embed() -> discord.Embed:
    """Build the About embed with centralized metadata."""

    embed = create_embed(
        title=f"{BOT_NAME} – About",
        description=BOT_DESCRIPTION,
        color=0xFFBB00,
    )

    embed.add_field(
        name="Bot Purpose",
        value="\n".join(f"• {item}" for item in BOT_PURPOSE_ITEMS),
        inline=False,
    )

    embed.add_field(
        name="Version",
        value=f"{BOT_VERSION}",
        inline=False,
    )

    embed.add_field(
        name="Privacy Summary",
        value=PRIVACY_SUMMARY,
        inline=False,
    )

    embed.add_field(
        name="User Rights",
        value=USER_RIGHTS_SUMMARY,
        inline=False,
    )

    embed.add_field(
        name="Support & Contact",
        value=f"{SUPPORT_TICKET_INFO}\nEmail: {SUPPORT_EMAIL}",
        inline=False,
    )

    embed.add_field(
        name="Full Privacy Policy",
        value=f"Read the full policy: {PRIVACY_POLICY_URL}",
        inline=False,
    )

    return embed


def create_token_embed(token: str, expires_unix: int) -> discord.Embed:
    """
    Creates an embed containing the verification token.

    Args:
        token (str): The verification token.
        expires_unix (int): UNIX timestamp when the token expires.

    Returns:
        discord.Embed: The token embed.
    """
    title = "📡 Account Verification"
    description = (
        "Use the **4-digit PIN** below for verification.\n\n"
        "**Instructions:**\n"
        ":one: Login and go to your [RSI account profile](https://robertsspaceindustries.com/account/profile).\n"
        '*If you see a "Restricted Access" message, please log in to your RSI account\n'
        ":two: Add the PIN to your **Short Bio** field.\n"
        ":three: Scroll down and click **Apply All Changes**.\n"
        ":four: Return here and click the 'Verify' button above.\n\n"
        "If you don't have an account, feel free to [enlist here]"
        "(https://robertsspaceindustries.com/enlist?referral=STAR-MXL7-VM6G).\n\n"
        f":information_source: *Note: The PIN expires <t:{expires_unix}:R>.*"
    )
    color = 0x00FF00  # Green

    embed = create_embed(title, description, color, DEFAULT_THUMBNAIL)
    embed.add_field(
        name="🔑 Your Verification PIN",
        value=f"```diff\n+ {token}\n```\n*On mobile, hold to copy*",
        inline=False,
    )

    embed.set_footer(
        text=(
            "By verifying, you consent to storing your RSI handle, community moniker (if found), "
            "and verification status for role assignment and username syncing."
        )
    )

    return embed


def create_error_embed(message: str) -> discord.Embed:
    """
    Creates an error embed.

    Args:
        message (str): The error message to display.

    Returns:
        discord.Embed: The created error embed.
    """
    title = "❌ Verification Failed"
    color = 0xFF0000  # Red
    return create_embed(title, message, color, DEFAULT_THUMBNAIL)


def create_success_embed(message: str) -> discord.Embed:
    """
    Creates a success embed.

    Args:
        message (str): The success message to display.

    Returns:
        discord.Embed: The created success embed.
    """
    title = "🎉 Verification Successful!"
    color = 0x00FF00  # Green
    return create_embed(title, message, color, DEFAULT_THUMBNAIL)


def create_cooldown_embed(wait_until: int) -> discord.Embed:
    """
    Creates a cooldown embed.

    Args:
        wait_until (int): UNIX timestamp when cooldown ends.

    Returns:
        discord.Embed: The cooldown embed.
    """
    title = "⏰ Cooldown Active"
    description = (
        "You have reached the maximum number of verification attempts.\n"
        f"Please try again <t:{wait_until}:R>."
    )
    color = 0xFFA500  # Orange
    return create_embed(title, description, color, DEFAULT_THUMBNAIL)


def build_welcome_description(
    role_type: str,
    org_name: str = "the organization",
    org_sid: str = DEFAULT_ORG_SID,
) -> str:
    """
    Return a role-specific welcome message.

    Uses Unicode emojis for portability. Messages are neutral and org-agnostic.

    Args:
        role_type: Membership status ('main', 'affiliate', 'non_member')
        org_name: Organization display name
        org_sid: Organization SID for RSI URLs

    Returns:
        Formatted welcome message string
    """
    if role_type == "main":
        return (
            f"🎉 **Welcome to {org_name}!**\n\n"
            f"You're verified as a **Main** member of **{org_name}**!\n\n"
            "Join our voice chats, explore events, and engage in our text channels to "
            "make the most of your experience!\n\n"
            "🫡 Fly safe!\n\n"
            "We set your Discord nickname to your RSI handle."
        )
    elif role_type == "affiliate":
        return (
            f"🎉 **Welcome to {org_name}!**\n\n"
            f"You're verified as an **Affiliate** member of **{org_name}**.\n\n"
            f"Consider setting **{org_sid}** as your Main Org:\n"
            ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
            f"Click **Set as Main** next to **{org_name}**.\n\n"
            "Join our voice chats, explore events, and engage in our text channels!\n\n"
            "🫡 Fly safe!\n\n"
            "We set your Discord nickname to your RSI handle."
        )
    elif role_type == "non_member":
        rsi_url = f"https://robertsspaceindustries.com/orgs/{org_sid}"
        return (
            f"👋 **Welcome!**\n\n"
            f"It looks like you're not yet a member of **{org_name}**.\n\n"
            f"🔗 [Join {org_name}]({rsi_url})\n"
            "Click **Enlist Now!** Membership requests are usually approved within "
            "24-72 hours. Reverify after approval to update your roles.\n\n"
            "In the meantime, join our voice chats and text channels!\n\n"
            "We set your Discord nickname to your RSI handle."
        )
    else:
        return (
            "Welcome to the server! You can verify again after 3 hours if needed.\n\n"
            "We set your Discord nickname to your RSI handle."
        )


def build_voice_settings_ui(
    snapshot: "VoiceSettingsSnapshot",
    user: discord.Member,
    active_channel: discord.VoiceChannel | None = None,
) -> discord.Embed:
    """
    Build a Discord embed showing voice channel settings from a snapshot.

    This is the unified UI renderer used by:
    - /voice list command
    - /voice admin_list command
    - Dashboard preview (converted to API response)

    Args:
        snapshot: VoiceSettingsSnapshot with resolved target names
        user: Discord member who owns the settings
        active_channel: Optional active voice channel

    Returns:
        Discord embed with formatted settings
    """

    # Determine if this is an active channel or saved settings
    is_active = snapshot.is_active and active_channel is not None

    if is_active and active_channel:
        title = "🎙️ Active Voice Channel Settings"
        description = f"Settings for {user.display_name}'s active channel: **{active_channel.name}**"
        color = discord.Color.green()
    else:
        title = "🎙️ Saved Voice Channel Settings"
        description = f"Saved settings for {user.display_name}"
        if snapshot.jtc_channel_id:
            description += f" (JTC: {snapshot.jtc_channel_id})"
        color = discord.Color.blue()

    embed = discord.Embed(title=title, description=description, color=color)

    # Basic settings section
    basic_settings = []
    if snapshot.channel_name:
        basic_settings.append(f"**Name:** {snapshot.channel_name}")
    if snapshot.user_limit is not None:
        limit_text = str(snapshot.user_limit) if snapshot.user_limit > 0 else "No limit"
        basic_settings.append(f"**User Limit:** {limit_text}")
    if snapshot.is_locked:
        basic_settings.append(
            f"**Lock:** {'🔒 Locked' if snapshot.is_locked else '🔓 Unlocked'}"
        )

    if basic_settings:
        embed.add_field(
            name="Channel Settings",
            value="\n".join(basic_settings),
            inline=False,
        )

    # Permission overrides section
    if snapshot.permissions:
        perm_text = []
        for perm in snapshot.permissions[:10]:  # Limit to prevent embed overflow
            emoji = "✅" if perm.permission == "permit" else "❌"
            target_display = perm.target_name
            if not target_display and perm.target_type == "role":
                target_display = get_role_display_name(user.guild, perm.target_id)
            if not target_display:
                target_display = f"Unknown ({perm.target_id})"
            perm_text.append(f"{emoji} **{target_display}:** {perm.permission}")

        if perm_text:
            embed.add_field(
                name="Permission Overrides",
                value="\n".join(perm_text),
                inline=False,
            )

    # Push-to-Talk section
    if snapshot.ptt_settings:
        ptt_text = []
        for ptt in snapshot.ptt_settings[:10]:
            status = "🔇 Required" if ptt.ptt_enabled else "🔊 Disabled"
            target_display = ptt.target_name
            if not target_display and ptt.target_type == "role":
                target_display = get_role_display_name(user.guild, ptt.target_id)
            if not target_display:
                target_display = f"Unknown ({ptt.target_id})"
            ptt_text.append(f"{status} for **{target_display}**")

        if ptt_text:
            embed.add_field(
                name="🎤 Push-to-Talk Overrides",
                value="\n".join(ptt_text),
                inline=False,
            )

    # Priority Speaker section
    if snapshot.priority_speaker_settings:
        priority_text = []
        for priority in snapshot.priority_speaker_settings[:10]:
            status = "✅ Enabled" if priority.priority_enabled else "❌ Disabled"
            target_display = priority.target_name
            if not target_display and priority.target_type == "role":
                target_display = get_role_display_name(user.guild, priority.target_id)
            if not target_display:
                target_display = f"Unknown ({priority.target_id})"
            priority_text.append(f"{status} for **{target_display}**")

        if priority_text:
            embed.add_field(
                name="📢 Priority Speaker Overrides",
                value="\n".join(priority_text),
                inline=False,
            )

    # Soundboard section
    if snapshot.soundboard_settings:
        soundboard_text = []
        for soundboard in snapshot.soundboard_settings[:10]:
            status = "✅ Enabled" if soundboard.soundboard_enabled else "❌ Disabled"
            target_display = soundboard.target_name
            if not target_display and soundboard.target_type == "role":
                target_display = get_role_display_name(user.guild, soundboard.target_id)
            if not target_display:
                target_display = f"Unknown ({soundboard.target_id})"
            soundboard_text.append(f"{status} for **{target_display}**")

        if soundboard_text:
            embed.add_field(
                name="🔊 Soundboard Overrides",
                value="\n".join(soundboard_text),
                inline=False,
            )

    embed.set_thumbnail(url=user.display_avatar.url)

    return embed


# -----------------------------------------------------------------------------
# Embed Factory Functions
# -----------------------------------------------------------------------------


def create_info_embed(
    title: str,
    description: str,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    footer: str | None = None,
    thumbnail_url: str | None = DEFAULT_THUMBNAIL,
) -> discord.Embed:
    """
    Create an informational embed with consistent styling.

    Args:
        title: Embed title
        description: Embed description
        fields: Optional list of (name, value, inline) tuples
        footer: Optional footer text
        thumbnail_url: Optional thumbnail URL

    Returns:
        Configured Discord embed
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=EmbedColors.INFO,
    )
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if footer:
        embed.set_footer(text=footer)
    return embed


def create_warning_embed(
    title: str,
    description: str,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """
    Create a warning embed with consistent styling.

    Args:
        title: Embed title (⚠️ added if not present)
        description: Embed description
        fields: Optional list of (name, value, inline) tuples

    Returns:
        Configured Discord embed
    """
    if not title.startswith("⚠"):
        title = f"⚠️ {title}"

    embed = discord.Embed(
        title=title,
        description=description,
        color=EmbedColors.WARNING,
    )
    embed.set_thumbnail(url=DEFAULT_THUMBNAIL)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed


def create_admin_embed(
    title: str,
    description: str,
    *,
    action_by: str | None = None,
    target: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """
    Create an admin action embed with consistent styling.

    Args:
        title: Embed title
        description: Embed description
        action_by: Username/ID of admin performing action
        target: Username/ID of target user
        fields: Optional additional fields

    Returns:
        Configured Discord embed
    """
    embed = discord.Embed(
        title=f"🔧 {title}",
        description=description,
        color=EmbedColors.ADMIN,
    )

    if action_by:
        embed.add_field(name="Admin", value=action_by, inline=True)
    if target:
        embed.add_field(name="Target", value=target, inline=True)

    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

    return embed


def create_status_embed(
    title: str,
    *,
    success_items: list[str] | None = None,
    warning_items: list[str] | None = None,
    error_items: list[str] | None = None,
    info_items: list[str] | None = None,
) -> discord.Embed:
    """
    Create a status summary embed with categorized items.

    Args:
        title: Embed title
        success_items: List of successful operations
        warning_items: List of warnings
        error_items: List of errors
        info_items: List of informational notes

    Returns:
        Configured Discord embed
    """
    # Determine overall color based on content
    if error_items:
        color = EmbedColors.ERROR
    elif warning_items:
        color = EmbedColors.WARNING
    else:
        color = EmbedColors.SUCCESS

    embed = discord.Embed(title=title, color=color)

    if success_items:
        embed.add_field(
            name="✅ Successful",
            value="\n".join(f"• {item}" for item in success_items[:10]),
            inline=False,
        )
    if warning_items:
        embed.add_field(
            name="⚠️ Warnings",
            value="\n".join(f"• {item}" for item in warning_items[:10]),
            inline=False,
        )
    if error_items:
        embed.add_field(
            name="❌ Errors",
            value="\n".join(f"• {item}" for item in error_items[:10]),
            inline=False,
        )
    if info_items:
        embed.add_field(
            name="ℹ️ Info",
            value="\n".join(f"• {item}" for item in info_items[:10]),
            inline=False,
        )

    return embed


def create_list_embed(
    title: str,
    items: list[str],
    *,
    description: str | None = None,
    empty_message: str = "No items found.",
    max_items: int = 20,
    color: int = EmbedColors.INFO,
) -> discord.Embed:
    """
    Create a list embed for displaying multiple items.

    Args:
        title: Embed title
        items: List of string items to display
        description: Optional description
        empty_message: Message to show if list is empty
        max_items: Maximum items to display
        color: Embed color

    Returns:
        Configured Discord embed
    """
    embed = discord.Embed(title=title, color=color)

    if description:
        embed.description = description

    if not items:
        embed.add_field(name="Results", value=empty_message, inline=False)
    else:
        items_text = "\n".join(f"• {item}" for item in items[:max_items])
        if len(items) > max_items:
            items_text += f"\n... and {len(items) - max_items} more"
        embed.add_field(name=f"Items ({len(items)})", value=items_text, inline=False)

    return embed


# -----------------------------------------------------------------------------
# Exported symbols
# -----------------------------------------------------------------------------

__all__ = [
    "DEFAULT_THUMBNAIL",
    "EmbedColors",
    "build_about_embed",
    "build_voice_settings_ui",
    "build_welcome_description",
    "create_admin_embed",
    "create_cooldown_embed",
    "create_embed",
    "create_error_embed",
    "create_info_embed",
    "create_list_embed",
    "create_status_embed",
    "create_success_embed",
    "create_token_embed",
    "create_verification_embed",
    "create_warning_embed",
]
