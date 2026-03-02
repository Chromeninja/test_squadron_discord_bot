-- Migration 006: Ticket form select-question support
-- NO-OP: The columns added here (input_type, options_json) are now defined
-- in migration 005's CREATE TABLE statement.  This migration is retained
-- for version-history continuity — existing databases that already ran 005
-- before those columns were added will have received them via the
-- application-layer schema-compat check in TicketFormService.

-- Original ALTER statements (disabled to prevent "duplicate column" errors
-- on fresh installs):
--
-- ALTER TABLE ticket_form_questions
--     ADD COLUMN input_type TEXT NOT NULL DEFAULT 'text'
--     CHECK (input_type IN ('text', 'select'));
--
-- ALTER TABLE ticket_form_questions
--     ADD COLUMN options_json TEXT NOT NULL DEFAULT '[]';

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (6);
