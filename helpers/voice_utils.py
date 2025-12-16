import contextlib

import discord

from helpers.discord_api import edit_channel
from helpers.permissions_helper import FEATURE_CONFIG
from services.db.repository import BaseRepository
from utils.logging import get_logger

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
    async with BaseRepository.transaction() as db:
        if guild_id and jtc_channel_id:
            # Query for specific guild and JTC channel - get the most recent active channel
            cursor = await db.execute(
                "SELECT voice_channel_id FROM voice_channels "
                "WHERE owner_id = ? AND guild_id = ? AND jtc_channel_id = ? AND is_active = 1 "
                "ORDER BY created_at DESC LIMIT 1",
                (user.id, guild_id, jtc_channel_id),
            )
        elif guild_id:
            # Query for specific guild - get the most recent active channel
            cursor = await db.execute(
                "SELECT voice_channel_id FROM voice_channels "
                "WHERE owner_id = ? AND guild_id = ? AND is_active = 1 "
                "ORDER BY created_at DESC LIMIT 1",
                (user.id, guild_id),
            )
        else:
            # Unscoped query across all channels, ordered by created_at to ensure
            # consistent behavior - get the most recent active channel
            cursor = await db.execute(
                "SELECT voice_channel_id FROM voice_channels "
                "WHERE owner_id = ? AND is_active = 1 "
                "ORDER BY created_at DESC LIMIT 1",
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
                        delete_query = "UPDATE voice_channels SET is_active = 0 WHERE voice_channel_id = ?"
                        delete_params = (channel_id,)
                        if guild_id and jtc_channel_id:
                            delete_query += " AND guild_id = ? AND jtc_channel_id = ?"
                            delete_params = (channel_id, guild_id, jtc_channel_id)
                        await db.execute(delete_query, delete_params)
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
        guild_id: Guild ID (required)
        jtc_channel_id: Join-to-create channel ID (required)
        **kwargs: Channel settings to update (channel_name, user_limit, lock)
    """
    if not guild_id or not jtc_channel_id:
        logger.error(
            "update_channel_settings requires both guild_id and jtc_channel_id"
        )
        return

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

    async with BaseRepository.transaction() as db:
        await db.execute(insert_query, insert_values)
        await db.execute(update_query, update_values)


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
        guild_id: Guild ID (required)
        jtc_channel_id: Join-to-create channel ID (required)
    """
    if not guild_id or not jtc_channel_id:
        logger.error(
            "set_voice_feature_setting requires both guild_id and jtc_channel_id"
        )
        return

    cfg = FEATURE_CONFIG.get(feature)
    if not cfg:
        logger.error(f"Unknown feature: {feature}")
        return

    db_table = cfg["db_table"]
    db_column = cfg["db_column"]

    t_id = target_id or 0

    query = f"""
        INSERT OR REPLACE INTO {db_table}
        (guild_id, jtc_channel_id, user_id, target_id, target_type, {db_column})
        VALUES (?, ?, ?, ?, ?, ?)
    """
    await BaseRepository.execute(
        query, (guild_id, jtc_channel_id, user_id, t_id, target_type, enable)
    )


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
        row = await BaseRepository.fetch_one(
            "SELECT owner_id FROM voice_channels WHERE voice_channel_id = ?",
            (channel.id,),
        )
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


def create_voice_settings_embed(
    settings, formatted, title: str, footer: str
) -> discord.Embed:
    embed = discord.Embed(title=title, color=discord.Color.blue())

    # Handle channel name
    channel_name = settings.get("channel_name", "Default Channel Name")
    embed.add_field(name="🗨️ Channel Name", value=channel_name, inline=False)

    # Handle lock state - convert boolean to string
    lock = settings.get("lock", False)
    lock_state = "🔒 Locked" if lock else "🔓 Unlocked"
    embed.add_field(name="🔒 Lock State", value=lock_state, inline=True)

    # Handle user limit
    user_limit = settings.get("user_limit", 0)
    limit_text = str(user_limit) if user_limit and user_limit > 0 else "No limit"
    embed.add_field(name="👥 User Limit", value=limit_text, inline=True)
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


def format_channel_settings(settings, interaction) -> dict[str, list[str]]:
    """
    Formats channel settings into text lines for embedding.
    """

    def format_target(tid, ttype) -> str:
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
    permissions = settings.get("permissions", settings.get("perm_rows", []))
    for tid, ttype, perm in permissions:
        permission_lines.append(f"- {format_target(tid, ttype)} => **{perm}**")
    if not permission_lines:
        permission_lines = ["No custom permissions set."]

    ptt_lines = []
    ptt_settings = settings.get("ptt_settings", settings.get("ptt_rows", []))
    for tid, ttype, enabled in ptt_settings:
        text = "Enabled" if enabled else "Disabled"
        ptt_lines.append(f"- {format_target(tid, ttype)} => **PTT {text}**")
    if not ptt_lines:
        ptt_lines = ["PTT is not configured."]

    priority_lines = []
    priority_settings = settings.get(
        "priority_settings", settings.get("priority_rows", [])
    )
    for tid, ttype, enabled in priority_settings:
        text = "Enabled" if enabled else "Disabled"
        priority_lines.append(
            f"- {format_target(tid, ttype)} => **PrioritySpeaker {text}**"
        )
    if not priority_lines:
        priority_lines = ["No priority speakers set."]

    soundboard_lines = []
    soundboard_settings = settings.get(
        "soundboard_settings", settings.get("soundboard_rows", [])
    )
    for tid, ttype, enabled in soundboard_settings:
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
