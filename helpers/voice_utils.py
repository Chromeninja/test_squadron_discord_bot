# Helpers/voice_utils.py

import contextlib

import discord
from services.db.database import Database
from utils.logging import get_logger

from helpers.discord_api import edit_channel, send_message
from helpers.permissions_helper import FEATURE_CONFIG

logger = get_logger(__name__)


async def get_user_channel(
    bot, user: discord.abc.User, guild_id=None, jtc_channel_id=None
) -> None:
    """
    Return the voice channel owned by this user, or None if none exists.
    Tries cache first, then fetches from the API. Cleans up stale mappings.

    Args:
        bot: The bot instance
        user: The user to find channels for
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
    """
    async with Database.get_connection() as db:
        if guild_id and jtc_channel_id:
            # Query for specific guild and JTC channel
            cursor = await db.execute(
                "SELECT voice_channel_id FROM user_voice_channels "
                "WHERE owner_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                (user.id, guild_id, jtc_channel_id),
            )
        elif guild_id:
            # Query for specific guild
            cursor = await db.execute(
                "SELECT voice_channel_id FROM user_voice_channels "
                "WHERE owner_id = ? AND guild_id = ? ORDER BY created_at DESC",
                (user.id, guild_id),
            )
        else:
            # Legacy query - all channels, ordered by created_at to ensure
            # consistent behavior
            cursor = await db.execute(
                "SELECT voice_channel_id FROM user_voice_channels "
                "WHERE owner_id = ? ORDER BY created_at DESC",
                (user.id,),
            )
        row = await cursor.fetchone()
        if row:
            channel_id = row[0]
            channel = bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except discord.NotFound:
                    logger.warning(
                        f"Channel with ID {channel_id} not found. Removing stale "
                        f"DB mapping."
                    )
                    with contextlib.suppress(Exception):
                        # Remove stale mapping so future checks don't keep trying
                        # to fetch
                        delete_query = (
                            "DELETE FROM user_voice_channels WHERE voice_channel_id = ?"
                        )
                        delete_params = (channel_id,)
                        if guild_id and jtc_channel_id:
                            delete_query += " AND guild_id = ? AND jtc_channel_id = ?"
                            delete_params = (channel_id, guild_id, jtc_channel_id)
                        await db.execute(delete_query, delete_params)
                        await db.commit()
                    return None
                except discord.HTTPException:
                    logger.exception(f"Failed to fetch channel {channel_id}")
                    return None

            return channel
    return None


def get_user_game_name(member) -> None:
    """
    Retrieves the name of the game the user is currently playing.
    """
    return next(
        (
            activity.name
            for activity in member.activities
            if activity.type == discord.ActivityType.playing
        ),
        None,
    )


async def update_channel_settings(
    user_id, guild_id=None, jtc_channel_id=None, **kwargs
) -> None:
    """
    Updates the channel settings (channel_name, user_limit, lock) for a user in DB.

    Args:
        user_id: The ID of the user
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
        **kwargs: Channel settings to update (channel_name, user_limit, lock)
    """
    fields = []
    values = []

    if "channel_name" in kwargs:
        fields.append("channel_name = ?")
        values.append(kwargs["channel_name"])
    if "user_limit" in kwargs:
        fields.append("user_limit = ?")
        values.append(kwargs["user_limit"])
    if "lock" in kwargs:
        fields.append("lock = ?")
        values.append(kwargs["lock"])

    if not fields:
        return

    # Build the query based on provided parameters
    if guild_id and jtc_channel_id:
        # Insert with guild and JTC channel IDs
        insert_query = (
            "INSERT OR IGNORE INTO channel_settings "
            "(guild_id, jtc_channel_id, user_id) VALUES (?, ?, ?)"
        )
        insert_values = (guild_id, jtc_channel_id, user_id)

        # Update with guild and JTC channel IDs
        update_query = (
            f"UPDATE channel_settings SET {', '.join(fields)} "
            f"WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?"
        )
        update_values = (*tuple(values), user_id, guild_id, jtc_channel_id)
    else:
        # Legacy mode (backward compatibility)
        insert_query = "INSERT OR IGNORE INTO channel_settings (user_id) VALUES (?)"
        insert_values = (user_id,)

        update_query = (
            f"UPDATE channel_settings SET {', '.join(fields)} WHERE user_id = ?"
        )
        update_values = (*tuple(values), user_id)

    async with Database.get_connection() as db:
        await db.execute(insert_query, insert_values)
        await db.execute(update_query, update_values)
        await db.commit()


async def set_voice_feature_setting(
    feature: str,
    user_id: int,
    target_id: int,
    target_type: str,
    enable: bool,
    guild_id=None,
    jtc_channel_id=None,
) -> None:
    """
    Inserts or updates the setting in the respective DB table for the given feature.
    feature can be "ptt", "priority_speaker", or "soundboard".

    Args:
        feature: The feature to set ("ptt", "priority_speaker", or "soundboard")
        user_id: The user ID who owns the channel
        target_id: The target user or role ID to apply the feature to
        target_type: The type of target ("user", "role", or "everyone")
        enable: Whether to enable or disable the feature
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
    """
    cfg = FEATURE_CONFIG.get(feature)
    if not cfg:
        logger.error(f"Unknown feature: {feature}")
        return

    db_table = cfg["db_table"]
    db_column = cfg["db_column"]

    t_id = target_id or 0

    if guild_id and jtc_channel_id:
        query = f"""
            INSERT OR REPLACE INTO {db_table}
            (guild_id, jtc_channel_id, user_id, target_id, target_type, {db_column})
            VALUES (?, ?, ?, ?, ?, ?)
        """
        async with Database.get_connection() as db:
            await db.execute(
                query, (guild_id, jtc_channel_id, user_id, t_id, target_type, enable)
            )
            await db.commit()
    else:
        # Legacy mode for backward compatibility
        query = f"""
            INSERT OR REPLACE INTO {db_table}
            (user_id, target_id, target_type, {db_column})
            VALUES (?, ?, ?, ?)
        """
        async with Database.get_connection() as db:
            await db.execute(query, (user_id, t_id, target_type, enable))
            await db.commit()


async def ensure_owner_overwrites(
    channel: discord.VoiceChannel, overwrites: dict
) -> None:
    """
    Ensure channel owner can still manage channels by setting appropriate overwrites.

    Args:
        channel: The voice channel
        overwrites: Dictionary of overwrites to modify in-place
    """
    try:
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT owner_id FROM user_voice_channels WHERE voice_channel_id = ?",
                (channel.id,),
            )
            row = await cursor.fetchone()
            if row:
                owner_id = row[0]
                if owner := channel.guild.get_member(owner_id):
                    ow = overwrites.get(owner, discord.PermissionOverwrite())
                    ow.manage_channels = True
                    ow.connect = True
                    overwrites[owner] = ow
    except Exception:
        logger.exception("Failed to set owner perms")


async def apply_voice_feature_toggle(
    channel: discord.VoiceChannel, feature: str, target, enable: bool
) -> None:
    """
    Applies the actual Overwrite on the channel for the given feature (ptt,
    priority_speaker, soundboard). 'target' can be a discord.Member, discord.Role,
    or default_role for "everyone".
    """
    cfg = FEATURE_CONFIG.get(feature)
    if not cfg:
        logger.error(f"Unknown feature: {feature}")
        return

    overwrites = channel.overwrites.copy()
    prop = cfg["overwrite_property"]
    final_value = not enable if cfg["inverted"] else enable
    # If 'target' is a single user or role or default_role
    overwrite = overwrites.get(target, discord.PermissionOverwrite())
    setattr(overwrite, prop, final_value)
    overwrites[target] = overwrite

    # Ensure channel owner can still manage channels
    await ensure_owner_overwrites(channel, overwrites)

    try:
        await edit_channel(channel, overwrites=overwrites)
        logger.info(
            f"Applied feature '{feature}'={enable} to channel '{channel.name}'."
        )
    except Exception:
        logger.exception(
            f"Failed to apply feature '{feature}' to channel '{channel.name}'"
        )

        # ------------------------------
        # Fetch & Format Channel Settings
        # ------------------------------


async def fetch_channel_settings(
    bot, interaction, allow_inactive=False, guild_id=None, jtc_channel_id=None
) -> None:
    """
    Fetch channel settings and permissions for the user's channel.
    If allow_inactive=True, we return DB info even if there's no active channel.

    Args:
        bot: The bot instance
        interaction: The interaction context
        allow_inactive: Whether to return settings even if the user doesn't have
            an active channel
        guild_id: Optional guild ID to filter by
        jtc_channel_id: Optional join-to-create channel ID to filter by
    """
    channel = await get_user_channel(bot, interaction.user, guild_id, jtc_channel_id)

    if not channel and not allow_inactive:
        await send_message(interaction, "You don't own a channel.", ephemeral=True)
        return None

    async with Database.get_connection() as db:
        if guild_id and jtc_channel_id:
            cursor = await db.execute(
                "SELECT channel_name, user_limit, lock FROM channel_settings "
                "WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                (interaction.user.id, guild_id, jtc_channel_id),
            )
        else:
            cursor = await db.execute(
                "SELECT channel_name, user_limit, lock FROM channel_settings "
                "WHERE user_id = ?",
                (interaction.user.id,),
            )
        row = await cursor.fetchone()

    if not row:
        return None

    channel_name = None
    user_limit = None
    lock_state = "Unlocked"

    db_channel_name = row[0]  # None if not set
    db_user_limit = row[1]  # 0=unlimited
    db_lock = row[2]  # 0=unlocked, 1=locked

    if channel:
        channel_name = db_channel_name or channel.name
        user_limit = db_user_limit or channel.user_limit
    else:
        channel_name = db_channel_name or f"{interaction.user.display_name}'s Channel"
        user_limit = db_user_limit or "No Limit"

    lock_state = "Locked" if db_lock == 1 else "Unlocked"

    # Fetch separate tables for permission, ptt, priority, soundboard
    perm_rows = await _fetch_settings_table(
        "channel_permissions", interaction.user.id, guild_id, jtc_channel_id
    )
    ptt_rows = await _fetch_settings_table(
        "channel_ptt_settings", interaction.user.id, guild_id, jtc_channel_id
    )
    priority_rows = await _fetch_settings_table(
        "channel_priority_speaker_settings",
        interaction.user.id,
        guild_id,
        jtc_channel_id,
    )
    soundboard_rows = await _fetch_settings_table(
        "channel_soundboard_settings", interaction.user.id, guild_id, jtc_channel_id
    )

    return {
        "channel_name": channel_name,
        "user_limit": user_limit,
        "lock_state": lock_state,
        "perm_rows": perm_rows,
        "ptt_rows": ptt_rows,
        "priority_rows": priority_rows,
        "soundboard_rows": soundboard_rows,
    }


async def _fetch_settings_table(
    table_name: str, user_id: int, guild_id=None, jtc_channel_id=None
) -> None:
    async with Database.get_connection() as db:
        if guild_id and jtc_channel_id:
            cursor = await db.execute(
                f"SELECT target_id, target_type, * FROM {table_name} "
                f"WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?",
                (user_id, guild_id, jtc_channel_id),
            )
        elif guild_id:
            cursor = await db.execute(
                f"SELECT target_id, target_type, * FROM {table_name} "
                f"WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
        else:
            cursor = await db.execute(
                f"SELECT target_id, target_type, * FROM {table_name} WHERE user_id = ?",
                (user_id,),
            )
        all_rows = await cursor.fetchall()

    return [(row[0], row[1], row[-1]) for row in all_rows]


def create_voice_settings_embed(
    settings, formatted, title: str, footer: str
) -> discord.Embed:
    embed = discord.Embed(title=title, color=discord.Color.blue())
    embed.add_field(
        name="🗨️ Channel Name", value=settings["channel_name"], inline=False
    )
    embed.add_field(name="🔒 Lock State", value=settings["lock_state"], inline=True)
    embed.add_field(
        name="👥 User Limit", value=str(settings["user_limit"]), inline=True
    )
    embed.add_field(
        name="✅ Permits/Rejects",
        value="\n".join(formatted["permission_lines"]),
        inline=False,
    )
    embed.add_field(
        name="🎙️ PTT Settings", value="\n".join(formatted["ptt_lines"]), inline=False
    )
    embed.add_field(
        name="📢 Priority Speaker",
        value="\n".join(formatted["priority_lines"]),
        inline=False,
    )
    embed.add_field(
        name="🔊 Soundboard",
        value="\n".join(formatted["soundboard_lines"]),
        inline=False,
    )
    embed.set_footer(text=footer)
    return embed


def format_channel_settings(settings, interaction) -> None:
    """
    Formats channel settings into text lines for embedding.
    """

    def format_target(tid, ttype) -> None:
        if ttype == "user":
            user = interaction.guild.get_member(tid)
            return user.mention if user else f"User ID: {tid}"
        if ttype == "role":
            role = interaction.guild.get_role(tid)
            return role.mention if role else f"Role ID: {tid}"
        if ttype == "everyone":
            return "**Everyone**"
        return f"Unknown: {tid}"

    permission_lines = []
    for tid, ttype, perm in settings["perm_rows"]:
        permission_lines.append(f"- {format_target(tid, ttype)} => **{perm}**")
    if not permission_lines:
        permission_lines = ["No custom permissions set."]

    ptt_lines = []
    for tid, ttype, enabled in settings["ptt_rows"]:
        text = "Enabled" if enabled else "Disabled"
        ptt_lines.append(f"- {format_target(tid, ttype)} => **PTT {text}**")
    if not ptt_lines:
        ptt_lines = ["PTT is not configured."]

    priority_lines = []
    for tid, ttype, enabled in settings["priority_rows"]:
        text = "Enabled" if enabled else "Disabled"
        priority_lines.append(
            f"- {format_target(tid, ttype)} => **PrioritySpeaker {text}**"
        )
    if not priority_lines:
        priority_lines = ["No priority speakers set."]

    soundboard_lines = []
    for tid, ttype, enabled in settings["soundboard_rows"]:
        text = "Enabled" if enabled else "Disabled"
        soundboard_lines.append(
            f"- {format_target(tid, ttype)} => **Soundboard {text}**"
        )
    if not soundboard_lines:
        soundboard_lines = ["Soundboard settings not customized."]

    return {
        "permission_lines": permission_lines,
        "ptt_lines": ptt_lines,
        "priority_lines": priority_lines,
        "soundboard_lines": soundboard_lines,
    }
