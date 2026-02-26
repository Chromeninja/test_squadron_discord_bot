-- Migration 007: Ticket category eligibility status support
-- Adds per-category allowed verification/org status restrictions.

ALTER TABLE ticket_categories
    ADD COLUMN allowed_statuses TEXT NOT NULL DEFAULT '[]';

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (7);
