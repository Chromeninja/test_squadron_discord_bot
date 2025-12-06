"""
Embed Helper Module

Provides utility functions for creating and formatting Discord embeds with
consistent styling and branding for the TEST Squadron Discord bot.
"""

from typing import TYPE_CHECKING

import discord

from helpers.permissions_helper import get_role_display_name
from utils.logging import get_logger

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot

# Initialize logger
logger = get_logger(__name__)


def create_embed(
    title: str,
    description: str,
    color: int = 0x00FF00,
    thumbnail_url: str = "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png",
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


def create_verification_embed() -> discord.Embed:
    """
    Creates the initial verification embed.

    Returns:
        discord.Embed: The verification embed.
    """
    title = "📡 Account Verification"
    description = (
        "Welcome! To get started, please **click the 'Get Token' button below**.\n\n"
        "After obtaining your token, verify your RSI / Star Citizen account by using the provided buttons.\n\n"
        "If you don't have an account, feel free to enlist here: "
        "https://robertsspaceindustries.com/enlist?referral=STAR-MXL7-VM6G"
    )
    color = 0xFFBB00  # Yellow
    thumbnail_url = (
        "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
    )
    return create_embed(title, description, color, thumbnail_url)


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
    thumbnail_url = (
        "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
    )

    embed = create_embed(title, description, color, thumbnail_url)
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
    thumbnail_url = (
        "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
    )
    return create_embed(title, message, color, thumbnail_url)


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
    thumbnail_url = (
        "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
    )
    return create_embed(title, message, color, thumbnail_url)


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
    thumbnail_url = (
        "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
    )
    return create_embed(title, description, color, thumbnail_url)


def build_welcome_description(role_type: str) -> str:
    """Return a role-specific welcome message."""
    if role_type == "main":
        base = (
            "<:testSquad:1332572066804928633> **Welcome, to TEST Squadron - "
            "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
            "We're thrilled to have you as a MAIN member of **TEST Squadron!**\n\n"
            "Join our voice chats, explore events, and engage in our text channels to "
            "make the most of your experience!\n\n"
            "Fly safe! <:o7:1332572027877593148>"
        )
        return base + "\n\nWe set your Discord nickname to your RSI handle."
    elif role_type == "affiliate":
        base = (
            "<:testSquad:1332572066804928633> **Welcome, to TEST Squadron - "
            "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
            "Your support helps us grow and excel. We encourage you to set **TEST** as "
            "your MAIN Org to show your loyalty.\n\n"
            "**Instructions:**\n"
            ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
            "1️⃣ Click **Set as Main** next to **TEST Squadron**.\n\n"
            "Join our voice chats, explore events, and engage in our text channels to get "
            "involved!\n\n"
            "<:o7:1332572027877593148>"
        )
        return base + "\n\nWe set your Discord nickname to your RSI handle."
    elif role_type == "non_member":
        base = (
            "<:testSquad:1332572066804928633> **Welcome, to TEST Squadron - "
            "Best Squadron!** <:BESTSquad:1332572087524790334>\n\n"
            "It looks like you're not yet a member of our org. <:what:1332572046638452736>\n\n"
            "Join us for thrilling adventures and be part of the best and biggest community!\n\n"
            "🔗 [Join TEST Squadron](https://robertsspaceindustries.com/orgs/TEST)\n"
            "*Click **Enlist Now!**. Test membership requests are usually approved within "
            "24-72 hours. You will need to reverify to update your roles once approved.*\n\n"
            "Join our voice chats, explore events, and engage in our text channels to get "
            "involved! <:o7:1332572027877593148>"
        )
        return base + "\n\nWe set your Discord nickname to your RSI handle."
    else:
        return "Welcome to the server! You can verify again after 3 hours if needed. We set your Discord nickname to your RSI handle."


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
