# helpers.py

import discord

def create_embed(title, description, color=0x00FF00, thumbnail_url=None):
    embed = discord.Embed(title=title, description=description, color=color)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed

def create_cooldown_embed(remaining_time, unit="minutes"):
    title = "⏰ Cooldown Active"
    if unit == "hours":
        description = f"You can verify again in {remaining_time} hours."
    elif unit == "minutes":
        description = f"You can verify again in {remaining_time} minutes."
    else:
        description = f"You can verify again in {remaining_time} seconds."
    return create_embed(title, description, color=0xFFA500)  # Orange color

def create_error_embed(message):
    title = "❌ Verification Failed"
    description = message
    return create_embed(title, description, color=0xFF0000)  # Red color

def create_success_embed(message):
    title = "🎉 Verification Successful!"
    description = message
    return create_embed(title, description, color=0x00FF00)  # Green color
