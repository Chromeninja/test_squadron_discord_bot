# Helpers/embeds.py

import discord
from helpers.logger import get_logger

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
    thumbnail_url = "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
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
    ":information_source: *Note: The PIN expires <t:{expires_unix}:R>.*"
    ).format(expires_unix=expires_unix)
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
                "By verifying, you consent to storing your RSI handle and verification "
                "status for role assignment purposes."
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
        return base + "\n\nWe set your Discord username to your RSI moniker if available; otherwise we use your RSI handle."
    if role_type == "affiliate":
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
        return base + "\n\nWe set your Discord username to your RSI moniker if available; otherwise we use your RSI handle."
    if role_type == "non_member":
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
        return base + "\n\nWe set your Discord username to your RSI moniker if available; otherwise we use your RSI handle."
    return "Welcome to the server! You can verify again after 3 hours if needed. We set your Discord username to your RSI moniker if available; otherwise we use your RSI handle."
