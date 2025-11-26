-- Migration: Add guild_id to announcement_events table
-- Date: 2025-11-25
-- Description: Adds guild_id column to announcement_events to support per-guild announcements
--
-- IMPORTANT: Before running this migration, manually flush all pending announcement_events
-- to avoid NULL guild_id issues. Use `/admin flush_announcements` command or wait for
-- automatic flush at configured UTC time.

-- Add guild_id column (nullable initially for safety)
ALTER TABLE announcement_events ADD COLUMN guild_id INTEGER;

-- Create index for efficient guild-based queries
CREATE INDEX IF NOT EXISTS idx_announcement_events_guild_id ON announcement_events(guild_id);

-- Future events MUST have guild_id, but legacy events can remain NULL and will be ignored
-- Consider adding: UPDATE announcement_events SET announced_at = ? WHERE announced_at IS NULL AND guild_id IS NULL
-- to mark old events as processed if needed after migration.
