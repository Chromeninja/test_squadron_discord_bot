-- Fix foreign key constraint issue after voice_channels schema change
BEGIN TRANSACTION;

-- Create new voice_channel_settings table with correct foreign key
CREATE TABLE voice_channel_settings_new (
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

-- Copy existing data (if any)
INSERT INTO voice_channel_settings_new 
SELECT guild_id, jtc_channel_id, owner_id, voice_channel_id, setting_key, setting_value 
FROM voice_channel_settings;

-- Drop the old table
DROP TABLE voice_channel_settings;

-- Rename the new table
ALTER TABLE voice_channel_settings_new RENAME TO voice_channel_settings;

-- Create indexes for performance
CREATE INDEX idx_voice_channel_settings_channel_id ON voice_channel_settings(voice_channel_id);
CREATE INDEX idx_voice_channel_settings_owner ON voice_channel_settings(guild_id, owner_id);

COMMIT;