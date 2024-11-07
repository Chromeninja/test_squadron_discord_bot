# helpers/embeds.py

import discord

def create_embed(title, description, color=0x00FF00, thumbnail_url=None):
    """
    Creates a Discord embed with the given parameters.

    Args:
        title (str): The title of the embed.
        description (str): The description/content of the embed.
        color (int, optional): The color of the embed in hexadecimal. Defaults to green.
        thumbnail_url (str, optional): URL of the thumbnail image. Defaults to None.

    Returns:
        discord.Embed: The created embed object.
    """
    embed = discord.Embed(title=title, description=description, color=color)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed

def create_error_embed(message):
    """
    Creates an error embed.

    Args:
        message (str): The error message to display.

    Returns:
        discord.Embed: The created error embed.
    """
    title = "❌ Verification Failed"
    description = message
    return create_embed(title, description, color=0xFF0000)  # Red color

def create_success_embed(message):
    """
    Creates a success embed.

    Args:
        message (str): The success message to display.

    Returns:
        discord.Embed: The created success embed.
    """
    title = "🎉 Verification Successful!"
    description = message
    return create_embed(title, description, color=0x00FF00)  # Green color
