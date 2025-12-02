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

    # Verification table (membership_status removed; status derived from org lists)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS verification (
            user_id INTEGER PRIMARY KEY,
            rsi_handle TEXT NOT NULL,
            last_updated INTEGER DEFAULT 0,
            verification_payload TEXT,
            needs_reverify INTEGER DEFAULT 0,
            needs_reverify_at INTEGER DEFAULT 0,
            community_moniker TEXT,
            main_orgs TEXT DEFAULT NULL,
            affiliate_orgs TEXT DEFAULT NULL
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

    # In-place migration: drop legacy membership_status column if it exists
    try:
        cur = await db.execute("PRAGMA table_info(verification)")
        rows = await cur.fetchall()
        cols = [r[1] for r in rows]
        if "membership_status" in cols:
            # Recreate table without membership_status while preserving data
            await db.execute("PRAGMA foreign_keys=OFF")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS _verification_new (
                    user_id INTEGER PRIMARY KEY,
                    rsi_handle TEXT NOT NULL,
                    last_updated INTEGER DEFAULT 0,
                    verification_payload TEXT,
                    needs_reverify INTEGER DEFAULT 0,
                    needs_reverify_at INTEGER DEFAULT 0,
                    community_moniker TEXT,
                    main_orgs TEXT DEFAULT NULL,
                    affiliate_orgs TEXT DEFAULT NULL
                )
                """
            )
            await db.execute(
                "INSERT INTO _verification_new(user_id, rsi_handle, last_updated, verification_payload, needs_reverify, needs_reverify_at, community_moniker, main_orgs, affiliate_orgs) "
                "SELECT user_id, rsi_handle, last_updated, verification_payload, needs_reverify, needs_reverify_at, community_moniker, main_orgs, affiliate_orgs FROM verification"
            )
            await db.execute("DROP TABLE verification")
            await db.execute("ALTER TABLE _verification_new RENAME TO verification")
            await db.execute("PRAGMA foreign_keys=ON")
    except Exception as e:
        logger.warning(f"Schema migration to drop verification.membership_status failed: {e}")

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

    # Audit trail for guild_settings changes
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by_user_id INTEGER,
            changed_at INTEGER DEFAULT (strftime('%s','now'))
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
            is_active INTEGER DEFAULT 1,
            previous_owner_id INTEGER
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
            timestamp INTEGER NOT NULL,
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

    # Index for faster cleanup queries on rate_limits
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_rate_limits_first_attempt ON rate_limits(action, first_attempt)"
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

    # Announcement events table
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS announcement_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT,
            event_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            announced_at INTEGER DEFAULT NULL
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_announcement_events_user_id ON announcement_events(user_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_announcement_events_guild_id ON announcement_events(guild_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_announcement_events_announced_at ON announcement_events(announced_at)"
    )

    # Lightweight in-place migration: add guild_id to announcement_events if missing
    try:
        cur = await db.execute("PRAGMA table_info(announcement_events)")
        cols = [row[1] for row in await cur.fetchall()]
        if "guild_id" not in cols:
            await db.execute("ALTER TABLE announcement_events ADD COLUMN guild_id INTEGER")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_announcement_events_guild_id ON announcement_events(guild_id)"
            )
    except Exception as e:
        logger.warning(f"Schema check/migration for announcement_events.guild_id failed: {e}")

    # Admin action audit log
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            admin_user_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_user_id TEXT,
            details TEXT,
            status TEXT DEFAULT 'success'
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_action_log_guild ON admin_action_log(guild_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_action_log_timestamp ON admin_action_log(timestamp)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_action_log_admin ON admin_action_log(admin_user_id)"
    )

    # Commit all schema changes
    await db.commit()

    logger.info("Schema initialization complete")
