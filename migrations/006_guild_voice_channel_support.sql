-- Migration 006: Guild Voice Channel Support

-- Create the guild_settings table
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (guild_id, key)
);

-- Alter existing tables to include guild_id and jtc_channel_id

-- 1. user_voice_channels
CREATE TABLE IF NOT EXISTS user_voice_channels_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    voice_channel_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
);

INSERT INTO user_voice_channels_new (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    owner_id, 
    voice_channel_id, 
    created_at 
FROM user_voice_channels;

DROP TABLE user_voice_channels;
ALTER TABLE user_voice_channels_new RENAME TO user_voice_channels;

-- 2. voice_cooldowns
CREATE TABLE IF NOT EXISTS voice_cooldowns_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
);

INSERT INTO voice_cooldowns_new (guild_id, jtc_channel_id, user_id, timestamp)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    user_id, 
    timestamp 
FROM voice_cooldowns;

DROP TABLE voice_cooldowns;
ALTER TABLE voice_cooldowns_new RENAME TO voice_cooldowns;

-- 3. channel_settings
CREATE TABLE IF NOT EXISTS channel_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_name TEXT,
    user_limit INTEGER DEFAULT 0,
    lock INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
);

INSERT INTO channel_settings_new (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    user_id, 
    channel_name, 
    user_limit, 
    lock 
FROM channel_settings;

DROP TABLE channel_settings;
ALTER TABLE channel_settings_new RENAME TO channel_settings;

-- 4. channel_permissions
CREATE TABLE IF NOT EXISTS channel_permissions_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    permission TEXT NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

INSERT INTO channel_permissions_new (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    user_id, 
    target_id, 
    target_type, 
    permission 
FROM channel_permissions;

DROP TABLE channel_permissions;
ALTER TABLE channel_permissions_new RENAME TO channel_permissions;

-- 5. channel_ptt_settings
CREATE TABLE IF NOT EXISTS channel_ptt_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    ptt_enabled INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

INSERT INTO channel_ptt_settings_new (guild_id, jtc_channel_id, user_id, target_id, target_type, ptt_enabled)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    user_id, 
    target_id, 
    target_type, 
    ptt_enabled 
FROM channel_ptt_settings;

DROP TABLE channel_ptt_settings;
ALTER TABLE channel_ptt_settings_new RENAME TO channel_ptt_settings;

-- 6. channel_priority_speaker_settings
CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    priority_enabled INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

INSERT INTO channel_priority_speaker_settings_new (guild_id, jtc_channel_id, user_id, target_id, target_type, priority_enabled)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    user_id, 
    target_id, 
    target_type, 
    priority_enabled 
FROM channel_priority_speaker_settings;

DROP TABLE channel_priority_speaker_settings;
ALTER TABLE channel_priority_speaker_settings_new RENAME TO channel_priority_speaker_settings;

-- 7. channel_soundboard_settings
CREATE TABLE IF NOT EXISTS channel_soundboard_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    soundboard_enabled INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

INSERT INTO channel_soundboard_settings_new (guild_id, jtc_channel_id, user_id, target_id, target_type, soundboard_enabled)
SELECT 
    (SELECT guild_id FROM guilds LIMIT 1) AS guild_id, 
    (SELECT value FROM settings WHERE key = 'join_to_create_channel_ids' LIMIT 1) AS jtc_channel_id, 
    user_id, 
    target_id, 
    target_type, 
    soundboard_enabled 
FROM channel_soundboard_settings;

DROP TABLE channel_soundboard_settings;
ALTER TABLE channel_soundboard_settings_new RENAME TO channel_soundboard_settings;

-- Create guilds table if it doesn't exist (for migration)
CREATE TABLE IF NOT EXISTS guilds (
    guild_id INTEGER PRIMARY KEY
);

-- Insert current guild to ensure migration works
INSERT OR IGNORE INTO guilds (guild_id) 
SELECT CAST(value AS INTEGER) FROM settings WHERE key = 'guild_id'
UNION
SELECT guild_id FROM (
    SELECT 0 AS guild_id
    WHERE NOT EXISTS (SELECT 1 FROM settings WHERE key = 'guild_id')
);
