-- Add guild_id column to announcement_events for per-guild announcements
ALTER TABLE announcement_events ADD COLUMN guild_id INTEGER;

-- Index to speed up per-guild scans
CREATE INDEX IF NOT EXISTS idx_announcement_events_guild_id ON announcement_events(guild_id);
