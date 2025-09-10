-- Migration: Add announcement_events table
-- Date: 2025-09-09
-- Description: Creates the announcement_events table needed for the announcement system

CREATE TABLE IF NOT EXISTS announcement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT,
    event_type TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    announced_at INTEGER DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_announcement_events_user_id ON announcement_events(user_id);
CREATE INDEX IF NOT EXISTS idx_announcement_events_announced_at ON announcement_events(announced_at);
