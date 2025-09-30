-- Migration 009: Support Multiple Channels Per Owner Per JTC
-- Transform the voice_channels table to allow multiple channels per owner per JTC

BEGIN TRANSACTION;

-- Safety check: Abort if new schema already exists to prevent conflicts
-- Check if voice_channels already has the new schema (id column + autoincrement)
SELECT CASE 
    WHEN EXISTS (
        SELECT 1 FROM sqlite_master 
        WHERE type = 'table' AND name = 'voice_channels'
        AND sql LIKE '%id INTEGER PRIMARY KEY AUTOINCREMENT%'
    )
    THEN RAISE(ABORT, 'Migration 009 already applied: voice_channels table already has new schema')
END;

-- First, check if we need to migrate from the old schema
-- If voice_channels table exists with PRIMARY KEY (guild_id, jtc_channel_id, owner_id),
-- we need to migrate the data

-- Create new voice_channels table with updated schema
CREATE TABLE IF NOT EXISTS voice_channels_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    voice_channel_id INTEGER NOT NULL UNIQUE,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    last_activity INTEGER DEFAULT (strftime('%s','now')),
    is_active INTEGER DEFAULT 1
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_voice_channels_new_guild_owner_active
ON voice_channels_new(guild_id, owner_id, is_active);

CREATE INDEX IF NOT EXISTS idx_voice_channels_new_guild_jtc_active
ON voice_channels_new(guild_id, jtc_channel_id, is_active);

-- Migrate data from old voice_channels table if it exists
INSERT OR IGNORE INTO voice_channels_new 
    (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
SELECT 
    guild_id, 
    jtc_channel_id, 
    owner_id, 
    voice_channel_id, 
    created_at, 
    last_activity, 
    is_active
FROM voice_channels 
WHERE EXISTS (
    SELECT 1 FROM sqlite_master 
    WHERE type = 'table' AND name = 'voice_channels'
);

-- Also migrate from user_voice_channels table if it exists (legacy support)
INSERT OR IGNORE INTO voice_channels_new 
    (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, is_active)
SELECT 
    guild_id, 
    jtc_channel_id, 
    owner_id, 
    voice_channel_id, 
    COALESCE(created_at, strftime('%s','now')),
    1
FROM user_voice_channels 
WHERE EXISTS (
    SELECT 1 FROM sqlite_master 
    WHERE type = 'table' AND name = 'user_voice_channels'
)
AND voice_channel_id NOT IN (SELECT voice_channel_id FROM voice_channels_new);

-- Verify data migration was successful before dropping old table
SELECT CASE 
    WHEN (SELECT COUNT(*) FROM voice_channels_new) < (
        SELECT COUNT(*) FROM voice_channels 
        WHERE EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'voice_channels')
    )
    THEN RAISE(ABORT, 'Data migration failed: voice_channels_new has fewer rows than voice_channels')
END;

-- Drop old table and rename new one
DROP TABLE IF EXISTS voice_channels;
ALTER TABLE voice_channels_new RENAME TO voice_channels;

-- Create new voice_channel_settings table with updated schema
CREATE TABLE IF NOT EXISTS voice_channel_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    voice_channel_id INTEGER NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT,
    PRIMARY KEY (guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key),
    FOREIGN KEY (voice_channel_id)
    REFERENCES voice_channels(voice_channel_id)
    ON DELETE CASCADE
);

-- Migrate settings data if old table exists
INSERT OR IGNORE INTO voice_channel_settings_new 
    (guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key, setting_value)
SELECT 
    vs.guild_id, 
    vs.jtc_channel_id, 
    vs.owner_id,
    vc.voice_channel_id,
    vs.setting_key, 
    vs.setting_value
FROM voice_channel_settings vs
JOIN voice_channels vc ON (
    vs.guild_id = vc.guild_id 
    AND vs.jtc_channel_id = vc.jtc_channel_id 
    AND vs.owner_id = vc.owner_id
)
WHERE EXISTS (
    SELECT 1 FROM sqlite_master 
    WHERE type = 'table' AND name = 'voice_channel_settings'
);

-- Verify settings migration was successful before dropping old table
SELECT CASE 
    WHEN EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'voice_channel_settings')
    AND (SELECT COUNT(*) FROM voice_channel_settings_new) < (SELECT COUNT(*) FROM voice_channel_settings)
    THEN RAISE(ABORT, 'Settings migration failed: voice_channel_settings_new has fewer rows than voice_channel_settings')
END;

-- Drop old settings table and rename new one
DROP TABLE IF EXISTS voice_channel_settings;
ALTER TABLE voice_channel_settings_new RENAME TO voice_channel_settings;

COMMIT;