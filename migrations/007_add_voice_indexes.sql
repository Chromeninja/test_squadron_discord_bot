-- Migration 007: Add indexes and constraints to voice tables

-- First, verify current migration version to prevent duplicate runs
BEGIN TRANSACTION;

-- Track this migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (7);

-- Add composite indexes for better query performance on voice tables

-- User voice channels: optimize owner+scope queries
CREATE INDEX IF NOT EXISTS idx_uvc_owner_scope ON user_voice_channels(owner_id, guild_id, jtc_channel_id);

-- Channel settings: optimize scope+user queries  
CREATE INDEX IF NOT EXISTS idx_cs_scope_user ON channel_settings(guild_id, jtc_channel_id, user_id);

-- Channel permissions: optimize scope+user+target queries
CREATE INDEX IF NOT EXISTS idx_cp_scope_user_target ON channel_permissions(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Channel PTT settings: optimize scope+user+target queries
CREATE INDEX IF NOT EXISTS idx_ptt_scope_user_target ON channel_ptt_settings(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Channel priority speaker settings: optimize scope+user+target queries  
CREATE INDEX IF NOT EXISTS idx_priority_scope_user_target ON channel_priority_speaker_settings(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Channel soundboard settings: optimize scope+user+target queries
CREATE INDEX IF NOT EXISTS idx_soundboard_scope_user_target ON channel_soundboard_settings(guild_id, jtc_channel_id, user_id, target_id, target_type);

-- Legacy indexes for backward compatibility
CREATE INDEX IF NOT EXISTS idx_channel_settings_lookup 
ON channel_settings(user_id, guild_id, jtc_channel_id);

CREATE INDEX IF NOT EXISTS idx_channel_permissions_lookup 
ON channel_permissions(user_id, guild_id, jtc_channel_id);

CREATE INDEX IF NOT EXISTS idx_channel_ptt_settings_lookup 
ON channel_ptt_settings(user_id, guild_id, jtc_channel_id);

CREATE INDEX IF NOT EXISTS idx_channel_priority_speaker_settings_lookup 
ON channel_priority_speaker_settings(user_id, guild_id, jtc_channel_id);

CREATE INDEX IF NOT EXISTS idx_channel_soundboard_settings_lookup 
ON channel_soundboard_settings(user_id, guild_id, jtc_channel_id);

-- voice_cooldowns index for timestamp-based cleanup
CREATE INDEX IF NOT EXISTS idx_voice_cooldowns_timestamp 
ON voice_cooldowns(last_creation);

-- SQLite doesn't support adding CHECK constraints to existing tables via ALTER TABLE,
-- so we'll need to enforce boolean values during write operations in the code.
-- For new installations, the schema.py will enforce these constraints.

COMMIT;
