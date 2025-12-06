-- Canonical schema for fresh deployments
PRAGMA foreign_keys=ON;

-- Migration tracking (single canonical version)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at INTEGER DEFAULT (strftime('%s','now'))
);
INSERT OR IGNORE INTO schema_migrations (version) VALUES (0);

-- Verification (membership_status removed; org data stored as JSON text)
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
);
CREATE INDEX IF NOT EXISTS idx_verification_user_id ON verification(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_rsi_handle ON verification(rsi_handle);
CREATE INDEX IF NOT EXISTS idx_verification_moniker ON verification(community_moniker);

-- Guild settings and audit trail
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (guild_id, key)
);
CREATE TABLE IF NOT EXISTS guild_settings_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by_user_id INTEGER,
    changed_at INTEGER DEFAULT (strftime('%s','now'))
);

-- Voice channels (authoritative table)
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
);
CREATE INDEX IF NOT EXISTS idx_voice_channels_owner ON voice_channels(owner_id, guild_id, jtc_channel_id);
CREATE INDEX IF NOT EXISTS idx_voice_channels_active ON voice_channels(guild_id, jtc_channel_id, is_active);
CREATE INDEX IF NOT EXISTS idx_voice_channels_voice_channel_id ON voice_channels(voice_channel_id);

-- Legacy user voice channels (kept for compatibility)
CREATE TABLE IF NOT EXISTS user_voice_channels (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    voice_channel_id INTEGER NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
);
CREATE INDEX IF NOT EXISTS idx_user_voice_channels_voice_channel_id ON user_voice_channels(voice_channel_id);
CREATE INDEX IF NOT EXISTS idx_uvc_owner_scope ON user_voice_channels(owner_id, guild_id, jtc_channel_id);

-- Voice cooldowns
CREATE TABLE IF NOT EXISTS voice_cooldowns (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
);

-- Channel settings
CREATE TABLE IF NOT EXISTS channel_settings (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_name TEXT,
    user_limit INTEGER,
    lock INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_cs_scope_user ON channel_settings(guild_id, jtc_channel_id, user_id);

-- Channel permissions
CREATE TABLE IF NOT EXISTS channel_permissions (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    permission TEXT NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);
CREATE INDEX IF NOT EXISTS idx_cp_scope_user_target ON channel_permissions(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Channel PTT settings
CREATE TABLE IF NOT EXISTS channel_ptt_settings (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    ptt_enabled BOOLEAN NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);
CREATE INDEX IF NOT EXISTS idx_ptt_scope_user_target ON channel_ptt_settings(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Channel priority speaker settings
CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    priority_enabled BOOLEAN NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);
CREATE INDEX IF NOT EXISTS idx_priority_scope_user_target ON channel_priority_speaker_settings(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Channel soundboard settings
CREATE TABLE IF NOT EXISTS channel_soundboard_settings (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    soundboard_enabled BOOLEAN NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);
CREATE INDEX IF NOT EXISTS idx_soundboard_scope_user_target ON channel_soundboard_settings(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Global settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Missing role warnings
CREATE TABLE IF NOT EXISTS missing_role_warnings (
    guild_id INTEGER PRIMARY KEY,
    reported_at INTEGER NOT NULL
);

-- Rate limits
CREATE TABLE IF NOT EXISTS rate_limits (
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 0,
    first_attempt INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, action)
);
CREATE INDEX IF NOT EXISTS idx_rate_limits_first_attempt ON rate_limits(action, first_attempt);

-- Auto recheck state
CREATE TABLE IF NOT EXISTS auto_recheck_state (
    user_id INTEGER PRIMARY KEY,
    last_auto_recheck INTEGER DEFAULT 0,
    next_retry_at INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    last_error TEXT
);

-- User JTC preferences
CREATE TABLE IF NOT EXISTS user_jtc_preferences (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_used_jtc_channel_id INTEGER NOT NULL,
    updated_at INTEGER DEFAULT (strftime('%s','now')),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_user_jtc_preferences_updated ON user_jtc_preferences(updated_at);

-- Announcement events
CREATE TABLE IF NOT EXISTS announcement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT,
    event_type TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    announced_at INTEGER DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_announcement_events_user_id ON announcement_events(user_id);
CREATE INDEX IF NOT EXISTS idx_announcement_events_guild_id ON announcement_events(guild_id);
CREATE INDEX IF NOT EXISTS idx_announcement_events_announced_at ON announcement_events(announced_at);

-- Admin action audit log
CREATE TABLE IF NOT EXISTS admin_action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    admin_user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user_id TEXT,
    details TEXT,
    status TEXT DEFAULT 'success'
);
CREATE INDEX IF NOT EXISTS idx_admin_action_log_guild ON admin_action_log(guild_id);
CREATE INDEX IF NOT EXISTS idx_admin_action_log_timestamp ON admin_action_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_admin_action_log_admin ON admin_action_log(admin_user_id);
