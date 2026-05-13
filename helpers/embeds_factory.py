"""
Embed Factory Functions — generic embed builders used across the app.

Contains EmbedColors, DEFAULT_THUMBNAIL, and status/factory embed functions.
Extracted from helpers/embeds.py to keep file sizes manageable.
Import from helpers.embeds for backward compatibility.
"""

from __future__ import annotations

import discord  # type: ignore[import-not-found]

# Standard thumbnail URL
DEFAULT_THUMBNAIL = (
    "https://testsquadron.com/styles/custom/logos/TEST-Simplified-Yellow.png"
)


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
    BLURPLE = 0x5865F2  # Discord blurple


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
