# helpers/embeds.py

import discord
from config.config_loader import ConfigLoader

def create_embed(title: str, description: str, color: int = 0x00FF00, thumbnail_url: str = None) -> discord.Embed:
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

def create_verification_embed() -> discord.Embed:
    """
    Creates the initial verification embed.

    Returns:
        discord.Embed: The verification embed.
    """
    config = ConfigLoader.load_config()
    title = config['embeds']['verification']['title']
    description = config['embeds']['verification']['description']
    color = int(config['embeds']['verification']['color'], 16)
    thumbnail_url = config['embeds']['verification']['thumbnail_url']
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
    config = ConfigLoader.load_config()
    title = config['embeds']['token']['title']
    description = config['embeds']['token']['description'].format(expires_unix=expires_unix)
    color = int(config['embeds']['token']['color'], 16)
    thumbnail_url = config['embeds']['token']['thumbnail_url']

    embed = create_embed(title, description, color, thumbnail_url)
    embed.add_field(
        name=config['embeds']['token']['field_name'],
        value=f"```diff\n+ {token}\n```\n*On mobile, hold to copy*",
        inline=False
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
    config = ConfigLoader.load_config()
    title = config['embeds']['error']['title']
    color = int(config['embeds']['error']['color'], 16)
    return create_embed(title, message, color)

def create_success_embed(message: str) -> discord.Embed:
    """
    Creates a success embed.

    Args:
        message (str): The success message to display.

    Returns:
        discord.Embed: The created success embed.
    """
    config = ConfigLoader.load_config()
    title = config['embeds']['success']['title']
    color = int(config['embeds']['success']['color'], 16)
    return create_embed(title, message, color)

def create_cooldown_embed(wait_until: int) -> discord.Embed:
    """
    Creates a cooldown embed.

    Args:
        wait_until (int): UNIX timestamp when cooldown ends.

    Returns:
        discord.Embed: The cooldown embed.
    """
    config = ConfigLoader.load_config()
    title = config['embeds']['cooldown']['title']
    description_template = config['embeds']['cooldown']['description']
    description = description_template.format(wait_until=wait_until)
    color = int(config['embeds']['cooldown']['color'], 16)
    return create_embed(title, description, color)
