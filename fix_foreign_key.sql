-- Fix foreign key constraint issue after voice_channels schema change
BEGIN TRANSACTION;

-- Temporarily disable foreign key constraints
PRAGMA foreign_keys = OFF;

-- Drop the problematic table (it's empty anyway)
DROP TABLE voice_channel_settings;

-- Recreate it with the correct foreign key reference
CREATE TABLE voice_channel_settings (
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

-- Create indexes
CREATE INDEX idx_voice_channel_settings_channel_id ON voice_channel_settings(voice_channel_id);
CREATE INDEX idx_voice_channel_settings_owner ON voice_channel_settings(guild_id, owner_id);

-- Re-enable foreign key constraints
PRAGMA foreign_keys = ON;

COMMIT;