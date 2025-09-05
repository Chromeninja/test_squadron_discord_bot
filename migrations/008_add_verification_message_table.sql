-- Migration: Add verification_message table for storing verification message IDs
-- Replaces JSON file-based storage with database persistence

CREATE TABLE IF NOT EXISTS verification_message (
    guild_id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    updated_at INTEGER DEFAULT (strftime('%s','now'))
);

-- Add index for faster lookups (though guild_id is already primary key)
CREATE INDEX IF NOT EXISTS idx_verification_message_guild_id ON verification_message(guild_id);

-- Add trigger to update updated_at on changes
CREATE TRIGGER IF NOT EXISTS update_verification_message_timestamp 
    AFTER UPDATE ON verification_message
BEGIN
    UPDATE verification_message SET updated_at = strftime('%s','now') WHERE guild_id = NEW.guild_id;
END;
