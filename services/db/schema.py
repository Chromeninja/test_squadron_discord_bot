# helpers/schema.py

"""
Schema definitions for the Discord bot's database.

This module centralizes all table creation logic to ensure consistency and avoid duplication.
"""

import aiosqlite

from utils.logging import get_logger

logger = get_logger(__name__)


async def init_schema(db: aiosqlite.Connection) -> None:
    """
    Initialize the database schema with all required tables.

    Args:
        db: An open database connection
    """
    # Enable foreign key constraints
    await db.execute("PRAGMA foreign_keys=ON")

    # Schema migrations tracking
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER DEFAULT (strftime('%s','now'))
        )
        """
    )

    # Verification table (keep shape expected by existing code/tests)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS verification (
            user_id INTEGER PRIMARY KEY,
            rsi_handle TEXT NOT NULL,
            membership_status TEXT,
            last_updated INTEGER DEFAULT 0,
            verification_payload TEXT,
            needs_reverify INTEGER DEFAULT 0,
            needs_reverify_at INTEGER DEFAULT 0,
            community_moniker TEXT
        )
        """
    )
    
    # Indexes for verification search performance
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_verification_user_id ON verification(user_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_verification_rsi_handle ON verification(rsi_handle)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_verification_moniker ON verification(community_moniker)"
    )

    # Guild settings
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (guild_id, key)
        )
        """
    )

    # Voice channels (new table replacing user_voice_channels)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            voice_channel_id INTEGER NOT NULL UNIQUE,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            last_activity INTEGER DEFAULT (strftime('%s','now')),
            is_active INTEGER DEFAULT 1
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_channels_owner ON voice_channels(owner_id, guild_id, jtc_channel_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_channels_active ON voice_channels(guild_id, jtc_channel_id, is_active)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_channels_voice_channel_id ON voice_channels(voice_channel_id)"
    )

    # User voice channels (legacy table - keeping for backward compatibility)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_voice_channels (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            voice_channel_id INTEGER NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_voice_channels_voice_channel_id ON user_voice_channels(voice_channel_id)"
    )
    # Add composite indexes for better query performance
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_uvc_owner_scope ON user_voice_channels(owner_id, guild_id, jtc_channel_id)"
    )

    # Voice cooldowns
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_cooldowns (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_creation INTEGER NOT NULL,
            PRIMARY KEY (guild_id, jtc_channel_id, user_id)
        )
        """
    )

    # Channel settings
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_settings (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_name TEXT,
            user_limit INTEGER,
            lock INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, jtc_channel_id, user_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cs_scope_user ON channel_settings(guild_id, jtc_channel_id, user_id)"
    )

    # Channel permissions
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_permissions (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,  -- 'user' or 'role' or 'everyone'
            permission TEXT NOT NULL,   -- 'permit' or 'reject'
            PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cp_scope_user_target ON channel_permissions(guild_id, jtc_channel_id, user_id, target_id, target_type)"
    )

    # Channel PTT settings
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_ptt_settings (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,  -- 'user', 'role', or 'everyone'
            ptt_enabled BOOLEAN NOT NULL,
            PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ptt_scope_user_target ON channel_ptt_settings(guild_id, jtc_channel_id, user_id, target_id, target_type)"
    )

    # Channel priority speaker settings
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,  -- 'user' or 'role'
            priority_enabled BOOLEAN NOT NULL,
            PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_priority_scope_user_target ON channel_priority_speaker_settings(guild_id, jtc_channel_id, user_id, target_id, target_type)"
    )

    # Channel soundboard settings
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_soundboard_settings (
            guild_id INTEGER NOT NULL,
            jtc_channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,  -- 'user', 'role', or 'everyone'
            soundboard_enabled BOOLEAN NOT NULL,
            PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_soundboard_scope_user_target ON channel_soundboard_settings(guild_id, jtc_channel_id, user_id, target_id, target_type)"
    )

    # Settings table (global)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # Missing role warnings table
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS missing_role_warnings (
            guild_id INTEGER PRIMARY KEY,
            reported_at INTEGER NOT NULL
        )
        """
    )

    # Rate limits table (primary key on user_id+action as expected by legacy code)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            attempt_count INTEGER DEFAULT 0,
            first_attempt INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, action)
        )
        """
    )

    # Auto-recheck state
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_recheck_state (
            user_id INTEGER PRIMARY KEY,
            last_auto_recheck INTEGER DEFAULT 0,
            next_retry_at INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            last_error TEXT
        )
        """
    )

    # User JTC preferences (for deterministic inactive channel selection)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_jtc_preferences (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_used_jtc_channel_id INTEGER NOT NULL,
            updated_at INTEGER DEFAULT (strftime('%s','now')),
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_jtc_preferences_updated ON user_jtc_preferences(updated_at)"
    )

    logger.info("Schema initialization complete")
