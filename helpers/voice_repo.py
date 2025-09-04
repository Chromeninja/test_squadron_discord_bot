"""
Voice Repository

This module provides a data access layer for voice-related database operations.
It abstracts away SQL queries and provides a consistent interface for the voice cog.
"""

from typing import Optional, List, Tuple, Dict, Any
from helpers.database import Database
from helpers.logger import get_logger

logger = get_logger(__name__)


async def get_user_channel_id(owner_id: int, guild_id: int, jtc_channel_id: int) -> Optional[int]:
    """
    Get the voice channel ID owned by a specific user in a specific guild and JTC context.
    
    Args:
        owner_id: The Discord user ID of the channel owner
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        
    Returns:
        The voice channel ID or None if not found
    """
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT voice_channel_id 
            FROM user_voice_channels 
            WHERE owner_id = ? AND guild_id = ? AND jtc_channel_id = ?
            """,
            (owner_id, guild_id, jtc_channel_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def upsert_channel_settings(user_id: int, guild_id: int, jtc_channel_id: int, **fields) -> None:
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
        
    async with Database.get_connection() as db:
        # First check if the record exists
        cursor = await db.execute(
            """
            SELECT 1 FROM channel_settings 
            WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
            """,
            (user_id, guild_id, jtc_channel_id),
        )
        exists = await cursor.fetchone()
        
        if exists:
            # Update existing record
            set_clause = ", ".join([f"{key} = ?" for key in fields.keys()])
            values = list(fields.values())
            values.extend([user_id, guild_id, jtc_channel_id])
            
            await db.execute(
                f"""
                UPDATE channel_settings 
                SET {set_clause} 
                WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                values,
            )
        else:
            # Insert new record
            columns = ["user_id", "guild_id", "jtc_channel_id"] + list(fields.keys())
            placeholders = ["?"] * len(columns)
            values = [user_id, guild_id, jtc_channel_id] + list(fields.values())
            
            await db.execute(
                f"""
                INSERT INTO channel_settings ({', '.join(columns)}) 
                VALUES ({', '.join(placeholders)})
                """,
                values,
            )
        
        await db.commit()


async def list_permissions(user_id: int, guild_id: int, jtc_channel_id: int, table_name: str) -> List[Dict[str, Any]]:
    """
    List permissions or settings from a specified table for a user's channel.
    
    Args:
        user_id: The Discord user ID
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        table_name: The name of the table to query (channel_permissions, channel_ptt_settings, etc.)
        
    Returns:
        A list of permission/setting entries
    """
    # Validate table name to prevent SQL injection
    valid_tables = [
        "channel_permissions", 
        "channel_ptt_settings",
        "channel_priority_speaker_settings",
        "channel_soundboard_settings"
    ]
    
    if table_name not in valid_tables:
        logger.error(f"Invalid table name: {table_name}")
        return []
    
    async with Database.get_connection() as db:
        cursor = await db.execute(
            f"""
            SELECT * FROM {table_name}
            WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
            """,
            (user_id, guild_id, jtc_channel_id),
        )
        
        columns = [desc[0] for desc in cursor.description]
        rows = await cursor.fetchall()
        
        return [dict(zip(columns, row)) for row in rows]


async def set_feature_row(
    table_name: str, 
    user_id: int, 
    guild_id: int, 
    jtc_channel_id: int, 
    target_id: int, 
    target_type: str, 
    enabled: bool
) -> None:
    """
    Set a feature permission row (PTT, Priority Speaker, Soundboard, or general permissions).
    
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
        "channel_soundboard_settings": ("soundboard_enabled", enabled)
    }
    
    if table_name not in valid_tables:
        logger.error(f"Invalid table name: {table_name}")
        return
    
    feature_column, feature_value = valid_tables[table_name]
    
    async with Database.get_connection() as db:
        # Check if row exists
        cursor = await db.execute(
            f"""
            SELECT 1 FROM {table_name} 
            WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ? AND target_id = ? AND target_type = ?
            """,
            (user_id, guild_id, jtc_channel_id, target_id, target_type),
        )
        exists = await cursor.fetchone()
        
        if exists:
            # Update existing row
            await db.execute(
                f"""
                UPDATE {table_name} 
                SET {feature_column} = ? 
                WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ? AND target_id = ? AND target_type = ?
                """,
                (feature_value, user_id, guild_id, jtc_channel_id, target_id, target_type),
            )
        else:
            # Insert new row
            await db.execute(
                f"""
                INSERT INTO {table_name} (user_id, guild_id, jtc_channel_id, target_id, target_type, {feature_column})
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, guild_id, jtc_channel_id, target_id, target_type, feature_value),
            )
        
        await db.commit()


async def transfer_channel_owner(
    voice_channel_id: int,
    new_owner_id: int,
    guild_id: int,
    jtc_channel_id: int
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
    async with Database.get_connection() as db:
        # Start a transaction
        await db.execute("BEGIN TRANSACTION")
        
        try:
            # Get current owner
            cursor = await db.execute(
                """
                SELECT owner_id FROM user_voice_channels 
                WHERE voice_channel_id = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (voice_channel_id, guild_id, jtc_channel_id),
            )
            row = await cursor.fetchone()
            
            if not row:
                logger.error(f"No channel found with ID {voice_channel_id}")
                await db.execute("ROLLBACK")
                return False
                
            current_owner_id = row[0]
            
            # Transfer channel ownership
            await db.execute(
                """
                UPDATE user_voice_channels 
                SET owner_id = ? 
                WHERE voice_channel_id = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (new_owner_id, voice_channel_id, guild_id, jtc_channel_id),
            )
            
            # Get current settings for the channel
            cursor = await db.execute(
                """
                SELECT channel_name, user_limit, lock FROM channel_settings 
                WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (current_owner_id, guild_id, jtc_channel_id),
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
                        (channel_name, user_limit, lock, new_owner_id, guild_id, jtc_channel_id),
                    )
                else:
                    # Insert new settings
                    await db.execute(
                        """
                        INSERT INTO channel_settings (user_id, guild_id, jtc_channel_id, channel_name, user_limit, lock)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (new_owner_id, guild_id, jtc_channel_id, channel_name, user_limit, lock),
                    )
            
            # Copy all permission entries
            tables_to_copy = [
                "channel_permissions",
                "channel_ptt_settings",
                "channel_priority_speaker_settings",
                "channel_soundboard_settings"
            ]
            
            for table in tables_to_copy:
                # Get all entries for the current owner
                cursor = await db.execute(
                    f"""
                    SELECT * FROM {table} 
                    WHERE user_id = ? AND guild_id = ? AND jtc_channel_id = ?
                    """,
                    (current_owner_id, guild_id, jtc_channel_id),
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
                            INSERT INTO {table} ({', '.join(columns)})
                            VALUES ({', '.join(placeholders)})
                            """,
                            new_entry,
                        )
            
            # Add or update voice cooldown for new owner
            await db.execute(
                """
                INSERT OR REPLACE INTO voice_cooldowns (guild_id, jtc_channel_id, user_id, timestamp)
                VALUES (?, ?, ?, strftime('%s','now'))
                """,
                (guild_id, jtc_channel_id, new_owner_id),
            )
            
            # Commit all changes
            await db.execute("COMMIT")
            return True
            
        except Exception as e:
            logger.error(f"Error transferring channel ownership: {e}")
            await db.execute("ROLLBACK")
            return False


async def get_stale_voice_entries(cutoff_time: int) -> List[Tuple[int, int, int]]:
    """
    Get a list of stale voice entries (guild_id, jtc_channel_id, user_id) for cleanup.
    
    Args:
        cutoff_time: Unix timestamp cutoff for stale entries
        
    Returns:
        List of (guild_id, jtc_channel_id, user_id) tuples
    """
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT guild_id, jtc_channel_id, user_id FROM voice_cooldowns 
            WHERE timestamp < ?
            """,
            (cutoff_time,),
        )
        rows = await cursor.fetchall()
        return [(row[0], row[1], row[2]) for row in rows]


async def cleanup_user_voice_data(guild_id: int, jtc_channel_id: int, user_id: int) -> None:
    """
    Clean up all voice data for a specific user in a specific guild and JTC context.
    
    Args:
        guild_id: The Discord guild ID
        jtc_channel_id: The join-to-create channel ID
        user_id: The Discord user ID
    """
    tables_to_delete = [
        "user_voice_channels",
        "channel_settings",
        "channel_permissions",
        "channel_ptt_settings",
        "channel_priority_speaker_settings",
        "channel_soundboard_settings",
        "voice_cooldowns",
    ]
    
    async with Database.get_connection() as db:
        for table in tables_to_delete:
            # user_voice_channels uses owner_id instead of user_id
            id_column = "owner_id" if table == "user_voice_channels" else "user_id"
            
            await db.execute(
                f"""
                DELETE FROM {table} 
                WHERE {id_column} = ? AND guild_id = ? AND jtc_channel_id = ?
                """,
                (user_id, guild_id, jtc_channel_id),
            )
        
        await db.commit()


async def cleanup_legacy_user_voice_data(user_id: int) -> None:
    """
    Clean up all voice data for a user using the legacy approach (user_id only).
    This is kept for backward compatibility and rollback purposes.
    
    Args:
        user_id: The Discord user ID
    """
    tables_to_delete = [
        ("user_voice_channels", "owner_id"),
        ("channel_settings", "user_id"),
        ("channel_permissions", "user_id"),
        ("channel_ptt_settings", "user_id"),
        ("channel_priority_speaker_settings", "user_id"),
        ("channel_soundboard_settings", "user_id"),
        ("voice_cooldowns", "user_id"),
    ]
    
    async with Database.get_connection() as db:
        for table, column in tables_to_delete:
            await db.execute(
                f"DELETE FROM {table} WHERE {column} = ?", 
                (user_id,)
            )
        
        await db.commit()
