"""
Voice Repository

This module provides a data access layer for voice-related database operations.
It abstracts away SQL queries and provides a consistent interface for the voice cog.

Note: Database imports are done lazily inside functions to avoid circular imports
through services/__init__.py -> VoiceService -> voice_repo.py
"""

import sqlite3
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)
ORPHAN_OWNER_ID = 0


async def get_user_channel_id(
    owner_id: int, guild_id: int, jtc_channel_id: int
) -> int | None:
    """
    Get the voice channel ID owned by a specific user in a specific guild and
    JTC context.

    Args:
        owner_id: The Discord user ID of the channel owner
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID

    Returns:
        The voice channel ID or None if not found
    """
    from services.db.repository import BaseRepository

    return await BaseRepository.fetch_value(
        """
        SELECT voice_channel_id
        FROM voice_channels
        WHERE owner_id = ? AND guild_id = ? AND jtc_channel_id = ? AND is_active = 1
        ORDER BY created_at DESC LIMIT 1
        """,
        (owner_id, guild_id, jtc_channel_id),
    )


async def get_owner_id_by_channel(voice_channel_id: int) -> int | None:
    """
    Get the owner ID for a voice channel by its ID.

    This function provides DB-first ownership verification, making it resilient
    to bot restarts and cache invalidation.

    Args:
        voice_channel_id: The Discord voice channel ID

    Returns:
        The owner's Discord user ID or None if channel not found or not managed
    """
    from services.db.repository import BaseRepository

    try:
        return await BaseRepository.fetch_value(
            """
            SELECT owner_id
            FROM voice_channels
            WHERE voice_channel_id = ? AND is_active = 1
            """,
            (voice_channel_id,),
        )
    except Exception as e:
        logger.exception(
            f"Error retrieving owner for channel {voice_channel_id}: {e}",
            exc_info=e,
        )
        return None


async def is_channel_owner(voice_channel_id: int, user_id: int) -> bool:
    """
    Check if a specific user is the owner of a voice channel.

    This is a convenience wrapper around get_owner_id_by_channel that returns
    a boolean result for ownership checks.

    Args:
        voice_channel_id: The Discord voice channel ID
        user_id: The Discord user ID to check

    Returns:
        True if the user owns the channel, False otherwise
    """
    owner_id = await get_owner_id_by_channel(voice_channel_id)
    return owner_id == user_id if owner_id is not None else False


async def upsert_channel_settings(
    user_id: int, guild_id: int, jtc_channel_id: int, **fields
) -> None:
    """
    Update or insert channel settings for a user.

    Args:
        user_id: The Discord user ID
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        **fields: Key-value pairs of settings to update
    """
    if not fields:
        logger.warning("No fields provided for upsert_channel_settings")
        return

    from services.db.repository import BaseRepository

    # First check if the record exists
    exists = await BaseRepository.exists(
        """
        SELECT 1 FROM channel_settings
        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
        """,
        (user_id, guild_id, jtc_channel_id),
    )

    if exists:
        # Update existing record
        set_clause = ", ".join([f"{key} = ?" for key in fields])
        values = list(fields.values())
        values.extend([user_id, guild_id, jtc_channel_id])

        await BaseRepository.execute(
            f"""
            UPDATE channel_settings
            SET {set_clause}
            WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
            """,
            tuple(values),
        )
    else:
        # Insert new record
        columns = ["user_id", "guild_id", "jtc_channel_id", *list(fields.keys())]
        placeholders = ["?"] * len(columns)
        values = [user_id, guild_id, jtc_channel_id, *list(fields.values())]

        await BaseRepository.execute(
            f"""
            INSERT INTO channel_settings ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            """,
            tuple(values),
        )


async def list_permissions(
    user_id: int, guild_id: int, jtc_channel_id: int, table_name: str
) -> list[dict[str, Any]]:
    """
    List permissions or settings from a specified table for a user's channel.

    Args:
        user_id: The Discord user ID
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        table_name: The name of the table to query (channel_permissions,
            channel_ptt_settings, etc.)

    Returns:
        A list of permission/setting entries
    """
    # Validate table name to prevent SQL injection
    valid_tables = [
        "channel_permissions",
        "channel_ptt_settings",
        "channel_priority_speaker_settings",
        "channel_soundboard_settings",
    ]

    if table_name not in valid_tables:
        logger.error(f"Invalid table name: {table_name}")
        return []

    from services.db.repository import BaseRepository

    rows = await BaseRepository.fetch_all(
        f"""
        SELECT * FROM {table_name}
        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
        """,
        (user_id, guild_id, jtc_channel_id),
    )
    return [dict(row) for row in rows]


async def set_feature_row(
    table_name: str,
    user_id: int,
    guild_id: int,
    jtc_channel_id: int,
    target_id: int,
    target_type: str,
    enabled: bool,
) -> None:
    """
    Set a feature permission row (PTT, Priority Speaker, Soundboard, or general
    permissions).

    Args:
        table_name: The name of the table to modify
        user_id: The Discord user ID (channel owner)
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        target_id: The target Discord ID (user, role, or 0 for everyone)
        target_type: The type of target ('user', 'role', or 'everyone')
        enabled: Whether the feature is enabled
    """
    # Validate table name to prevent SQL injection
    valid_tables = {
        "channel_permissions": ("permission", "permit" if enabled else "reject"),
        "channel_ptt_settings": ("ptt_enabled", enabled),
        "channel_priority_speaker_settings": ("priority_enabled", enabled),
        "channel_soundboard_settings": ("soundboard_enabled", enabled),
    }

    if table_name not in valid_tables:
        logger.error(f"Invalid table name: {table_name}")
        return

    feature_column, feature_value = valid_tables[table_name]

    from services.db.repository import BaseRepository

    # Check if row exists
    exists = await BaseRepository.exists(
        f"""
        SELECT 1 FROM {table_name}
        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
            AND target_id = ? AND target_type = ?
        """,
        (user_id, guild_id, jtc_channel_id, target_id, target_type),
    )

    if exists:
        # Update existing row
        await BaseRepository.execute(
            f"""
            UPDATE {table_name}
            SET {feature_column} = ?
            WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                AND target_id = ? AND target_type = ?
            """,
            (
                feature_value,
                user_id,
                guild_id,
                jtc_channel_id,
                target_id,
                target_type,
            ),
        )
    else:
        # Insert new row
        await BaseRepository.execute(
            f"""
            INSERT INTO {table_name}
            (user_id, guild_id, jtc_channel_id, target_id, target_type, {feature_column})
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                guild_id,
                jtc_channel_id,
                target_id,
                target_type,
                feature_value,
            ),
        )


async def transfer_channel_owner(
    voice_channel_id: int, new_owner_id: int, guild_id: int, jtc_channel_id: int
) -> bool:
    """
    Transfer ownership of a voice channel to a new user.

    Args:
        voice_channel_id: The voice channel ID
        new_owner_id: The new owner's Discord user ID
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID

    Returns:
        True if transfer was successful, False otherwise
    """
    from services.db.repository import BaseRepository

    try:
        async with BaseRepository.transaction() as db:
            # Get current owner
            cursor = await db.execute(
                """
                SELECT owner_id, previous_owner_id FROM voice_channels
                WHERE voice_channel_id = ? AND guild_id = ? AND jtc_channel_id = ? AND is_active = 1
                """,
                (voice_channel_id, guild_id, jtc_channel_id),
            )
            row = await cursor.fetchone()

            if not row:
                logger.error(f"No channel found with ID {voice_channel_id}")
                return False

            current_owner_id, previous_owner_id = row
            effective_owner_id = (
                previous_owner_id
                if current_owner_id == ORPHAN_OWNER_ID and previous_owner_id
                else current_owner_id
            )

            # Transfer channel ownership
            await db.execute(
                """
                UPDATE voice_channels
                SET owner_id = ?, previous_owner_id = NULL
                WHERE voice_channel_id = ? AND guild_id = ? AND jtc_channel_id = ? AND is_active = 1
                """,
                (new_owner_id, voice_channel_id, guild_id, jtc_channel_id),
            )

            # Get current settings for the channel
            cursor = await db.execute(
                """
                SELECT channel_name, user_limit, lock FROM channel_settings
                WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (effective_owner_id, guild_id, jtc_channel_id),
            )
            settings_row = await cursor.fetchone()

            if settings_row:
                # Copy settings to new owner
                channel_name, user_limit, lock = settings_row

                # Check if new owner already has settings
                cursor = await db.execute(
                    """
                    SELECT 1 FROM channel_settings
                    WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                    """,
                    (new_owner_id, guild_id, jtc_channel_id),
                )
                has_settings = await cursor.fetchone()

                if has_settings:
                    # Update existing settings
                    await db.execute(
                        """
                        UPDATE channel_settings
                        SET channel_name = ?, user_limit = ?, lock = ?
                        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                        """,
                        (
                            channel_name,
                            user_limit,
                            lock,
                            new_owner_id,
                            guild_id,
                            jtc_channel_id,
                        ),
                    )
                else:
                    # Insert new settings
                    await db.execute(
                        """
                        INSERT INTO channel_settings
                        (user_id, guild_id, jtc_channel_id, channel_name, user_limit, lock)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_owner_id,
                            guild_id,
                            jtc_channel_id,
                            channel_name,
                            user_limit,
                            lock,
                        ),
                    )

            # Copy all permission entries
            tables_to_copy = [
                "channel_permissions",
                "channel_ptt_settings",
                "channel_priority_speaker_settings",
                "channel_soundboard_settings",
            ]

            for table in tables_to_copy:
                # Get all entries for the current owner
                cursor = await db.execute(
                    f"""
                    SELECT * FROM {table}
                    WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                    """,
                    (effective_owner_id, guild_id, jtc_channel_id),
                )
                entries = await cursor.fetchall()

                if entries:
                    # Get column names
                    columns = [desc[0] for desc in cursor.description]
                    col_indices = {col: idx for idx, col in enumerate(columns)}

                    # Delete existing entries for new owner if any
                    await db.execute(
                        f"""
                        DELETE FROM {table}
                        WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                        """,
                        (new_owner_id, guild_id, jtc_channel_id),
                    )

                    # Insert new entries
                    for entry in entries:
                        # Create a new entry with the new owner ID
                        new_entry = list(entry)
                        new_entry[col_indices["user_id"]] = new_owner_id

                        placeholders = ["?"] * len(columns)
                        await db.execute(
                            f"""
                            INSERT INTO {table} ({", ".join(columns)})
                            VALUES ({", ".join(placeholders)})
                            """,
                            new_entry,
                        )

            # Add or update voice cooldown for new owner
            await db.execute(
                """
                INSERT OR REPLACE INTO voice_cooldowns
                (guild_id, jtc_channel_id, user_id, timestamp)
                VALUES (?, ?, ?, strftime('%s','now'))
                """,
                (guild_id, jtc_channel_id, new_owner_id),
            )

            # Transaction auto-commits on success
            return True

    except sqlite3.OperationalError as exc:
        logger.warning(
            "Voice tables unavailable while transferring ownership (channel=%s): %s",
            voice_channel_id,
            exc,
        )
        return False
    except Exception:
        logger.exception("Error transferring channel ownership")
        return False


async def get_stale_voice_entries(cutoff_time: int) -> list[tuple[int, int, int]]:
    """
    Get a list of stale voice entries (guild_id, jtc_channel_id, user_id) for cleanup.

    Args:
        cutoff_time: Unix timestamp cutoff for stale entries

    Returns:
        List of (guild_id, jtc_channel_id, user_id) tuples
    """
    from services.db.repository import BaseRepository

    rows = await BaseRepository.fetch_all(
        """
        SELECT guild_id, jtc_channel_id, user_id FROM voice_cooldowns
        WHERE timestamp < ?
        """,
        (cutoff_time,),
    )
    return [(row[0], row[1], row[2]) for row in rows]


async def cleanup_user_voice_data(
    guild_id: int, jtc_channel_id: int, user_id: int
) -> None:
    """
    Clean up all voice data for a specific user in a specific guild and JTC context.

    Args:
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        user_id: The Discord user ID
    """
    tables_to_delete = [
        "voice_channels",
        "channel_settings",
        "channel_permissions",
        "channel_ptt_settings",
        "channel_priority_speaker_settings",
        "channel_soundboard_settings",
        "voice_cooldowns",
    ]

    from services.db.repository import BaseRepository

    async with BaseRepository.transaction() as db:
        for table in tables_to_delete:
            # voice_channels uses owner_id instead of user_id
            id_column = "owner_id" if table == "voice_channels" else "user_id"

            await db.execute(
                f"""
                DELETE FROM {table}
                WHERE {id_column} = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (user_id, guild_id, jtc_channel_id),
            )


async def cleanup_user_voice_data_unscoped(user_id: int) -> None:
    """
    Clean up all voice data for a user using the user_id-only path.

    Args:
        user_id: The Discord user ID
    """
    tables_to_delete = [
        ("voice_channels", "owner_id"),
        ("channel_settings", "user_id"),
        ("channel_permissions", "user_id"),
        ("channel_ptt_settings", "user_id"),
        ("channel_priority_speaker_settings", "user_id"),
        ("channel_soundboard_settings", "user_id"),
        ("voice_cooldowns", "user_id"),
    ]

    # Validate table and column names against whitelist for security
    valid_tables_columns = {
        "channel_permissions": "user_id",
        "channel_ptt_settings": "user_id",
        "channel_priority_speaker_settings": "user_id",
        "channel_soundboard_settings": "user_id",
        "voice_cooldowns": "user_id",
    }

    from services.db.repository import BaseRepository

    async with BaseRepository.transaction() as db:
        for table, column in tables_to_delete:
            # Security check: validate table and column names
            if valid_tables_columns.get(table) != column:
                logger.error(f"Invalid table/column combination: {table}.{column}")
                continue

            # Safe to use string formatting since we validated against whitelist
            await db.execute(f"DELETE FROM {table} WHERE {column} = ?", (user_id,))
