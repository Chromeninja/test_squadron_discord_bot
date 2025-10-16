"""
Centralized Discord reply helpers for consistent message delivery.

This module provides helpers to ensure:
- All slash-command errors/successes are ephemeral
- Passive bot-initiated notices are sent via DM
- Consistent formatting across all user-facing messages
"""

from typing import Optional

import discord

from utils.logging import get_logger

logger = get_logger(__name__)


async def send_user_error(
    interaction: discord.Interaction, text: str, ephemeral: bool = True
) -> None:
    """
    Send an error message to the user via interaction followup.

    This is for slash-command error responses. All errors are ephemeral by default
    to avoid cluttering channels with error messages.

    Args:
        interaction: Discord interaction from the slash command
        text: Error message text (should already include ❌ prefix)
        ephemeral: Whether to send as ephemeral (default: True)

    Example:
        await send_user_error(interaction, "❌ **Owner is still present**\\nYou can't claim this channel.")
    """
    try:
        # Ensure text has error emoji if not present
        if not text.startswith("❌"):
            text = f"❌ {text}"

        await interaction.followup.send(text, ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.error(f"Failed to send error message to user: {e}")
    except Exception as e:
        logger.exception("Unexpected error sending user error", exc_info=e)


async def send_user_success(
    interaction: discord.Interaction, text: str, ephemeral: bool = True
) -> None:
    """
    Send a success message to the user via interaction followup.

    This is for slash-command success responses. Most successes are ephemeral
    to keep channels clean, but some may be public (e.g., announcements).

    Args:
        interaction: Discord interaction from the slash command
        text: Success message text (should already include ✅ prefix)
        ephemeral: Whether to send as ephemeral (default: True)

    Example:
        await send_user_success(interaction, "✅ Successfully claimed ownership of voice channel!")
    """
    try:
        # Ensure text has success emoji if not present
        if not text.startswith("✅"):
            text = f"✅ {text}"

        await interaction.followup.send(text, ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.error(f"Failed to send success message to user: {e}")
    except Exception as e:
        logger.exception("Unexpected error sending user success", exc_info=e)


async def send_user_info(
    interaction: discord.Interaction, text: str, ephemeral: bool = True
) -> None:
    """
    Send an informational message to the user via interaction followup.

    This is for slash-command informational responses (e.g., help text, status).

    Args:
        interaction: Discord interaction from the slash command
        text: Info message text
        ephemeral: Whether to send as ephemeral (default: True)

    Example:
        await send_user_info(interaction, "📋 Here are your voice channel settings...")
    """
    try:
        await interaction.followup.send(text, ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.error(f"Failed to send info message to user: {e}")
    except Exception as e:
        logger.exception("Unexpected error sending user info", exc_info=e)


async def dm_user(member: discord.Member, text: str) -> bool:
    """
    Send a direct message to a user (for bot-initiated, non-slash events).

    This is for passive notifications like:
    - "You're creating channels too fast" (rate limit warning)
    - Background warnings or notices
    - Any bot-initiated message that isn't a slash command response

    Failures are logged but don't raise exceptions. Returns True on success.

    Args:
        member: Discord member to send DM to
        text: Message text (should include appropriate emoji prefix)

    Returns:
        True if DM was sent successfully, False otherwise

    Example:
        await dm_user(member, "⚠️ You're creating channels too fast. Please wait 5s.")
    """
    try:
        await member.send(text)
        logger.debug(f"Sent DM to {member.display_name}: {text[:50]}...")
        return True
    except discord.Forbidden:
        # User has DMs disabled or blocked the bot
        logger.debug(
            f"Cannot send DM to {member.display_name} (DMs disabled or bot blocked)"
        )
        return False
    except discord.HTTPException as e:
        # Other Discord API errors
        logger.warning(f"Failed to send DM to {member.display_name}: {e}")
        return False
    except Exception as e:
        # Unexpected errors
        logger.exception(f"Unexpected error sending DM to {member.display_name}", exc_info=e)
        return False


async def send_embed_error(
    interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = True
) -> None:
    """
    Send an error embed to the user via interaction followup.

    Use this for more detailed error messages that benefit from embed formatting.

    Args:
        interaction: Discord interaction from the slash command
        embed: Discord embed (should use red color for errors)
        ephemeral: Whether to send as ephemeral (default: True)
    """
    try:
        # Ensure embed has error color
        if embed.color != discord.Color.red():
            embed.color = discord.Color.red()

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.error(f"Failed to send error embed to user: {e}")
    except Exception as e:
        logger.exception("Unexpected error sending error embed", exc_info=e)


async def send_embed_success(
    interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = True
) -> None:
    """
    Send a success embed to the user via interaction followup.

    Use this for more detailed success messages that benefit from embed formatting.

    Args:
        interaction: Discord interaction from the slash command
        embed: Discord embed (should use green color for success)
        ephemeral: Whether to send as ephemeral (default: True)
    """
    try:
        # Ensure embed has success color
        if embed.color != discord.Color.green():
            embed.color = discord.Color.green()

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.error(f"Failed to send success embed to user: {e}")
    except Exception as e:
        logger.exception("Unexpected error sending success embed", exc_info=e)


async def send_embed_info(
    interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = True
) -> None:
    """
    Send an informational embed to the user via interaction followup.

    Use this for detailed informational messages (e.g., settings lists, help pages).

    Args:
        interaction: Discord interaction from the slash command
        embed: Discord embed (should use blue color for info)
        ephemeral: Whether to send as ephemeral (default: True)
    """
    try:
        # Ensure embed has info color
        if embed.color != discord.Color.blue():
            embed.color = discord.Color.blue()

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.error(f"Failed to send info embed to user: {e}")
    except Exception as e:
        logger.exception("Unexpected error sending info embed", exc_info=e)
