-- Migration 006: Ticket form select-question support
-- Adds question type and option payload storage for dropdown-based intake steps.

ALTER TABLE ticket_form_questions
    ADD COLUMN input_type TEXT NOT NULL DEFAULT 'text'
    CHECK (input_type IN ('text', 'select'));

ALTER TABLE ticket_form_questions
    ADD COLUMN options_json TEXT NOT NULL DEFAULT '[]';

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (6);
