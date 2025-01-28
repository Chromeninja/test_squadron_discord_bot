# helpers/voice_utils.py

import discord
from helpers.database import Database
from helpers.logger import get_logger
from helpers.discord_api import send_message, edit_channel
from helpers.permissions_helper import FEATURE_CONFIG

logger = get_logger(__name__)

async def get_user_channel(bot, member):
    """
    Retrieves the voice channel owned by the user.
    """
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT voice_channel_id FROM user_voice_channels WHERE owner_id = ?",
            (member.id,)
        )
        row = await cursor.fetchone()
        if row:
            channel_id = row[0]
            channel = bot.get_channel(channel_id)
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
    """
    for activity in member.activities:
        if activity.type == discord.ActivityType.playing:
            return activity.name
    return None

async def update_channel_settings(user_id, **kwargs):
    """
    Updates the channel settings (channel_name, user_limit, lock) for a user in DB.
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

# -------------------------------------------------------------------------
# UNIFIED FEATURE TOGGLE: ptt, priority_speaker, soundboard
# -------------------------------------------------------------------------

async def set_voice_feature_setting(feature: str, user_id: int, target_id: int, target_type: str, enable: bool):
    """
    Inserts or updates the setting in the respective DB table for the given feature.
    feature can be "ptt", "priority_speaker", or "soundboard".
    """
    cfg = FEATURE_CONFIG.get(feature)
    if not cfg:
        logger.error(f"Unknown feature: {feature}")
        return

    db_table = cfg["db_table"]
    db_column = cfg["db_column"]

    t_id = target_id if target_id else 0

    query = f"""
        INSERT OR REPLACE INTO {db_table} (user_id, target_id, target_type, {db_column})
        VALUES (?, ?, ?, ?)
    """
    async with Database.get_connection() as db:
        await db.execute(query, (user_id, t_id, target_type, enable))
        await db.commit()

async def apply_voice_feature_toggle(channel: discord.VoiceChannel, feature: str, target, enable: bool):
    """
    Applies the actual Overwrite on the channel for the given feature (ptt, priority_speaker, soundboard).
    'target' can be a discord.Member, discord.Role, or default_role for "everyone".
    """
    cfg = FEATURE_CONFIG.get(feature)
    if not cfg:
        logger.error(f"Unknown feature: {feature}")
        return

    overwrites = channel.overwrites.copy()
    prop = cfg["overwrite_property"]
    final_value = enable
    if cfg["inverted"]:
        final_value = not enable

    # If 'target' is a single user or role or default_role
    overwrite = overwrites.get(target, discord.PermissionOverwrite())
    setattr(overwrite, prop, final_value)
    overwrites[target] = overwrite

    # Ensure channel owner can still manage channels
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel.id,)
            )
            row = await cursor.fetchone()
            if row:
                owner_id = row[0]
                owner = channel.guild.get_member(owner_id)
                if owner:
                    ow = overwrites.get(owner, discord.PermissionOverwrite())
                    ow.manage_channels = True
                    ow.connect = True
                    overwrites[owner] = ow
    except Exception as e:
        logger.error(f"Failed to set owner perms: {e}")

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(f"Applied feature '{feature}'={enable} to channel '{channel.name}'.")
    except Exception as e:
        logger.exception(f"Failed to apply feature '{feature}' to channel '{channel.name}': {e}")


# ------------------------------
#  Fetch & Format Channel Settings
# ------------------------------

async def fetch_channel_settings(bot, interaction, allow_inactive=False):
    """
    Fetch channel settings and permissions for the user's channel.
    If allow_inactive=True, we return DB info even if there's no active channel.
    """
    channel = await get_user_channel(bot, interaction.user)
    
    if not channel and not allow_inactive:
        await send_message(interaction, "You don't own a channel.", ephemeral=True)
        return None

    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT channel_name, user_limit, lock FROM channel_settings WHERE user_id = ?",
            (interaction.user.id,)
        )
        row = await cursor.fetchone()

    if not row:
        return None

    channel_name = None
    user_limit = None
    lock_state = "Unlocked"

    db_channel_name = row[0] # None if not set
    db_user_limit  = row[1] # 0=unlimited
    db_lock        = row[2] # 0=unlocked, 1=locked

    if channel:
        channel_name = db_channel_name if db_channel_name else channel.name
        user_limit   = db_user_limit  if db_user_limit  else channel.user_limit
    else:
        channel_name = db_channel_name or f"{interaction.user.display_name}'s Channel"
        user_limit   = db_user_limit  or "No Limit"

    lock_state = "Locked" if db_lock == 1 else "Unlocked"

    # Fetch separate tables for permission, ptt, priority, soundboard
    perm_rows = await _fetch_settings_table("channel_permissions", interaction.user.id)
    ptt_rows = await _fetch_settings_table("channel_ptt_settings", interaction.user.id)
    priority_rows = await _fetch_settings_table("channel_priority_speaker_settings", interaction.user.id)
    soundboard_rows = await _fetch_settings_table("channel_soundboard_settings", interaction.user.id)

    return {
        "channel_name": channel_name,
        "user_limit": user_limit,
        "lock_state": lock_state,
        "perm_rows": perm_rows,
        "ptt_rows": ptt_rows,
        "priority_rows": priority_rows,
        "soundboard_rows": soundboard_rows,
    }

async def _fetch_settings_table(table_name: str, user_id: int):
    async with Database.get_connection() as db:
        cursor = await db.execute(
            f"SELECT target_id, target_type, * FROM {table_name} WHERE user_id = ?",
            (user_id,)
        )
        all_rows = await cursor.fetchall()

    results = []
    for row in all_rows:
        feature_bool = row[-1] 
        target_id = row[0]
        target_type = row[1]
        results.append((target_id, target_type, feature_bool))
    return results

def format_channel_settings(settings, interaction):
    """
    Formats channel settings into text lines for embedding.
    """
    def format_target(tid, ttype):
        if ttype == "user":
            user = interaction.guild.get_member(tid)
            return user.mention if user else f"User ID: {tid}"
        elif ttype == "role":
            role = interaction.guild.get_role(tid)
            return role.mention if role else f"Role ID: {tid}"
        elif ttype == "everyone":
            return "**Everyone**"
        return f"Unknown: {tid}"

    permission_lines = []
    for (tid, ttype, perm) in settings["perm_rows"]:
        permission_lines.append(f"- {format_target(tid, ttype)} => **{perm}**")
    if not permission_lines:
        permission_lines = ["No custom permissions set."]

    ptt_lines = []
    for (tid, ttype, enabled) in settings["ptt_rows"]:
        text = "Enabled" if enabled else "Disabled"
        ptt_lines.append(f"- {format_target(tid, ttype)} => **PTT {text}**")
    if not ptt_lines:
        ptt_lines = ["PTT is not configured."]

    priority_lines = []
    for (tid, ttype, enabled) in settings["priority_rows"]:
        text = "Enabled" if enabled else "Disabled"
        priority_lines.append(f"- {format_target(tid, ttype)} => **PrioritySpeaker {text}**")
    if not priority_lines:
        priority_lines = ["No priority speakers set."]

    soundboard_lines = []
    for (tid, ttype, enabled) in settings["soundboard_rows"]:
        text = "Enabled" if enabled else "Disabled"
        soundboard_lines.append(f"- {format_target(tid, ttype)} => **Soundboard {text}**")
    if not soundboard_lines:
        soundboard_lines = ["Soundboard settings not customized."]

    return {
        "permission_lines": permission_lines,
        "ptt_lines": ptt_lines,
        "priority_lines": priority_lines,
        "soundboard_lines": soundboard_lines,
    }
