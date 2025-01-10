# helpers/voice_utils.py

import discord
from helpers.database import Database
from helpers.logger import get_logger
from helpers.discord_api import send_message, send_message

logger = get_logger(__name__)

async def get_user_channel(bot, member):
    """
    Retrieves the voice channel owned by the user.

    Args:
        bot: The bot instance.
        member: The Discord member.

    Returns:
        The voice channel owned by the user, or None if not found.
    """
    # Fetch the channel ID from the database
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT voice_channel_id FROM user_voice_channels WHERE owner_id = ?",
            (member.id,)
        )
        row = await cursor.fetchone()
        if row:
            channel_id = row[0]
            channel = bot.get_channel(channel_id)

            # Attempt to fetch channel if not cached
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except discord.NotFound:
                    logger.warning(f"Channel with ID {channel_id} not found.")
                    return None
                except discord.Forbidden:
                    logger.warning(f"Forbidden to fetch channel with ID {channel_id}.")
                    return None
                except discord.HTTPException as e:
                    logger.error(f"Failed to fetch channel {channel_id}: {e}")
                    return None
            return channel
    return None

def get_user_game_name(member):
    """
    Retrieves the name of the game the user is currently playing.

    Args:
        member: The Discord member.

    Returns:
        The name of the game the user is playing, or None if not playing any.
    """
    for activity in member.activities:
        if activity.type == discord.ActivityType.playing:
            return activity.name
    return None

async def update_channel_settings(user_id, **kwargs):
    """
    Updates the channel settings for a user.

    Args:
        user_id (int): The Discord user ID.
        **kwargs: The settings to update (channel_name, user_limit, lock).
    """
    fields = []
    values = []

    if 'channel_name' in kwargs:
        fields.append("channel_name = ?")
        values.append(kwargs['channel_name'])
    if 'user_limit' in kwargs:
        fields.append("user_limit = ?")
        values.append(kwargs['user_limit'])
    if 'lock' in kwargs:
        fields.append("lock = ?")
        values.append(kwargs['lock'])

    if not fields:
        return

    values.append(user_id)

    query = f"UPDATE channel_settings SET {', '.join(fields)} WHERE user_id = ?"

    async with Database.get_connection() as db:
        await db.execute("INSERT OR IGNORE INTO channel_settings (user_id) VALUES (?)", (user_id,))
        await db.execute(query, tuple(values))
        await db.commit()

async def set_channel_permission(user_id, target_id, target_type, permission):
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_permissions (user_id, target_id, target_type, permission)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id, target_type, permission)
        )
        await db.commit()

async def remove_channel_permission(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute(
            """
            DELETE FROM channel_permissions
            WHERE user_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, target_id, target_type)
        )
        await db.commit()

async def get_channel_permissions(user_id):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT target_id, target_type, permission
            FROM channel_permissions
            WHERE user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchall()

async def set_ptt_setting(user_id, target_id, target_type, ptt_enabled):
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_ptt_settings
            (user_id, target_id, target_type, ptt_enabled)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id if target_id is not None else 0, target_type, ptt_enabled)
        )
        await db.commit()

async def remove_ptt_setting(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute(
            """
            DELETE FROM channel_ptt_settings
            WHERE user_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, target_id, target_type)
        )
        await db.commit()

async def get_ptt_settings(user_id):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT target_id, target_type, ptt_enabled
            FROM channel_ptt_settings
            WHERE user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchall()

# ======================
# Priority Speaker
# ======================
async def set_priority_speaker_setting(user_id, target_id, target_type, priority_enabled: bool):
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_priority_speaker_settings 
            (user_id, target_id, target_type, priority_enabled)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id if target_id else 0, target_type, priority_enabled)
        )
        await db.commit()

async def remove_priority_speaker_setting(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute(
            """
            DELETE FROM channel_priority_speaker_settings
            WHERE user_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, target_id, target_type)
        )
        await db.commit()

async def get_priority_speaker_settings(user_id: int):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT target_id, target_type, priority_enabled
            FROM channel_priority_speaker_settings
            WHERE user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchall()

# ======================
# Soundboard
# ======================
async def set_soundboard_setting(user_id, target_id, target_type, soundboard_enabled: bool):
    async with Database.get_connection() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO channel_soundboard_settings 
            (user_id, target_id, target_type, soundboard_enabled)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, target_id if target_id else 0, target_type, soundboard_enabled)
        )
        await db.commit()

async def remove_soundboard_setting(user_id, target_id, target_type):
    async with Database.get_connection() as db:
        await db.execute(
            """
            DELETE FROM channel_soundboard_settings
            WHERE user_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, target_id, target_type)
        )
        await db.commit()

async def get_soundboard_settings(user_id: int):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT target_id, target_type, soundboard_enabled
            FROM channel_soundboard_settings
            WHERE user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchall()

async def fetch_channel_settings(bot, interaction):
    """
    Fetch channel settings and permissions for the user's channel.

    Returns:
        A dictionary of channel settings and permissions, or None if the user doesn't own a channel.
    """
    channel = await get_user_channel(bot, interaction.user)
    if not channel:
        await send_message(interaction, "You don't own a channel.", ephemeral=True)
        return None

    # Fetch basic channel settings
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT channel_name, user_limit, lock FROM channel_settings WHERE user_id = ?",
            (interaction.user.id,)
        )
        row = await cursor.fetchone()

        channel_name = row[0] if (row and row[0]) else channel.name
        user_limit = row[1] if row else channel.user_limit
        lock_state = "Locked" if (row and row[2] == 1) else "Unlocked"

    # Fetch permissions, PTT, Priority Speaker, and Soundboard settings
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT target_id, target_type, permission FROM channel_permissions WHERE user_id = ?",
            (interaction.user.id,)
        )
        perm_rows = await cursor.fetchall()

        cursor = await db.execute(
            "SELECT target_id, target_type, ptt_enabled FROM channel_ptt_settings WHERE user_id = ?",
            (interaction.user.id,)
        )
        ptt_rows = await cursor.fetchall()

        cursor = await db.execute(
            "SELECT target_id, target_type, priority_enabled FROM channel_priority_speaker_settings WHERE user_id = ?",
            (interaction.user.id,)
        )
        priority_rows = await cursor.fetchall()

        cursor = await db.execute(
            "SELECT target_id, target_type, soundboard_enabled FROM channel_soundboard_settings WHERE user_id = ?",
            (interaction.user.id,)
        )
        soundboard_rows = await cursor.fetchall()

    return {
        "channel_name": channel_name,
        "user_limit": user_limit,
        "lock_state": lock_state,
        "perm_rows": perm_rows,
        "ptt_rows": ptt_rows,
        "priority_rows": priority_rows,
        "soundboard_rows": soundboard_rows,
    }

def format_channel_settings(settings, interaction):
    """
    Formats channel settings into a dictionary of lines for embedding.

    Args:
        settings: The dictionary returned by `fetch_channel_settings`.
        interaction: The Discord interaction for accessing guild members/roles.

    Returns:
        A dictionary of formatted text lines.
    """
    def format_target(target_id, target_type):
        if target_type == "user":
            user = interaction.guild.get_member(target_id)
            return user.mention if user else f"User ID: {target_id}"
        elif target_type == "role":
            role = interaction.guild.get_role(target_id)
            return role.mention if role else f"Role ID: {target_id}"
        elif target_type == "everyone":
            return "**Everyone**"
        return f"Unknown: {target_id}"

    permission_lines = [
        f"- {format_target(target_id, target_type)} => **{permission}**"
        for target_id, target_type, permission in settings["perm_rows"]
    ] or ["No custom permissions set."]

    ptt_lines = [
        f"- {format_target(target_id, target_type)} => **PTT {'Enabled' if ptt_enabled else 'Disabled'}**"
        for target_id, target_type, ptt_enabled in settings["ptt_rows"]
    ] or ["PTT is not configured."]

    priority_lines = [
        f"- {format_target(target_id, target_type)} => **PrioritySpeaker {'Enabled' if priority_enabled else 'Disabled'}**"
        for target_id, target_type, priority_enabled in settings["priority_rows"]
    ] or ["No priority speakers set."]

    soundboard_lines = [
        f"- {format_target(target_id, target_type)} => **Soundboard {'Enabled' if sb_enabled else 'Disabled'}**"
        for target_id, target_type, sb_enabled in settings["soundboard_rows"]
    ] or ["Soundboard settings not customized."]

    return {
        "permission_lines": permission_lines,
        "ptt_lines": ptt_lines,
        "priority_lines": priority_lines,
        "soundboard_lines": soundboard_lines,
    }
