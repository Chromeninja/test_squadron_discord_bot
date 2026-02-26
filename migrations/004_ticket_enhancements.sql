-- Migration 004: Ticket system enhancements
-- Adds: claim/assign, close reason, initial description, reopen tracking

-- Claim / assign support
ALTER TABLE tickets ADD COLUMN claimed_by INTEGER;
ALTER TABLE tickets ADD COLUMN claimed_at INTEGER;

-- Close reason (from modal)
ALTER TABLE tickets ADD COLUMN close_reason TEXT;

-- Initial description (from ticket creation modal)
ALTER TABLE tickets ADD COLUMN initial_description TEXT;

-- Reopen tracking
ALTER TABLE tickets ADD COLUMN reopened_at INTEGER;
ALTER TABLE tickets ADD COLUMN reopened_by INTEGER;
