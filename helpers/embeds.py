"""
Embed Helper Module

Provides utility functions for creating and formatting Discord embeds with
consistent styling and branding for the TEST Clanker Discord bot.
"""


import discord  # type: ignore[import-not-found]

from helpers.constants import DEFAULT_ORG_SID
from helpers.embeds_factory import (
    DEFAULT_THUMBNAIL,
    EmbedColors,
    create_admin_embed,
    create_info_embed,
    create_list_embed,
    create_status_embed,
    create_warning_embed,
)
from helpers.embeds_voice import build_voice_settings_ui
from utils.about_metadata import (
    BOT_DESCRIPTION,
    BOT_NAME,
    BOT_PURPOSE_ITEMS,
    BOT_VERSION,
    DATA_RETENTION_SUMMARY,
    LEGAL_BASIS_SUMMARY,
    PRIVACY_POLICY_URL,
    PRIVACY_REQUEST_STEPS,
    PRIVACY_SUMMARY,
    SUPPORT_EMAIL,
    SUPPORT_TICKET_INFO,
    USER_RIGHTS_SUMMARY,
)
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)


def create_embed(
    title: str,
    description: str,
    color: int = EmbedColors.SUCCESS,
    thumbnail_url: str = DEFAULT_THUMBNAIL,
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
    color = EmbedColors.VERIFICATION
    return create_embed(title, description, color, thumbnail_url or DEFAULT_THUMBNAIL)


def build_about_embed() -> discord.Embed:
    """Build the About embed with centralized metadata."""

    embed = create_embed(
        title=f"{BOT_NAME} – About",
        description=BOT_DESCRIPTION,
        color=EmbedColors.PRIMARY,
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


def build_privacy_embed() -> discord.Embed:
    """Build the Privacy & Data Rights embed."""

    embed = create_embed(
        title=f"{BOT_NAME} – Privacy & Data Rights",
        description=(
            "Use this guide for data-access and deletion requests. "
            "For complete details, see the full policy link below."
        ),
        color=EmbedColors.PRIMARY,
    )

    embed.add_field(
        name="Legal Basis",
        value=LEGAL_BASIS_SUMMARY,
        inline=False,
    )

    embed.add_field(
        name="What We Process",
        value=PRIVACY_SUMMARY,
        inline=False,
    )

    embed.add_field(
        name="Your Rights",
        value=USER_RIGHTS_SUMMARY,
        inline=False,
    )

    embed.add_field(
        name="How To Request",
        value="\n".join(f"• {step}" for step in PRIVACY_REQUEST_STEPS),
        inline=False,
    )

    embed.add_field(
        name="Retention",
        value=DATA_RETENTION_SUMMARY,
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
    color = EmbedColors.SUCCESS

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
    color = EmbedColors.ERROR
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
    color = EmbedColors.SUCCESS
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
    color = EmbedColors.WARNING
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
