-- Migration 008: Add deleted_at column to tickets table
-- Tracks when a ticket's Discord thread was deleted (thread cleanup).
-- The ticket database record is preserved for analytics; only the
-- Discord thread is removed.

ALTER TABLE tickets ADD COLUMN deleted_at INTEGER DEFAULT NULL;

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (8);
