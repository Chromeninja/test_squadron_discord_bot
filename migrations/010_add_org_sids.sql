-- Migration: Add main_orgs and affiliate_orgs columns to verification table
-- Date: 2025-11-25
-- Description: Adds JSON array columns to store organization SIDs for main and affiliate orgs.
--              These columns enable cross-guild verification tracking by storing RSI organization
--              identifiers (SIDs) separately, allowing membership status to be derived from the
--              org lists. Hidden/redacted orgs are stored as the literal string "REDACTED".

-- Add main_orgs column to store JSON array of main organization SIDs
-- Format: JSON array of strings, e.g., ["TEST"] or ["REDACTED"]
-- NULL or empty array [] indicates no data yet populated (will be backfilled by auto-recheck)
ALTER TABLE verification ADD COLUMN main_orgs TEXT DEFAULT NULL;

-- Add affiliate_orgs column to store JSON array of affiliate organization SIDs  
-- Format: JSON array of strings, e.g., ["XVII", "AVOCADO", "REDACTED"]
-- NULL or empty array [] indicates no data yet populated (will be backfilled by auto-recheck)
ALTER TABLE verification ADD COLUMN affiliate_orgs TEXT DEFAULT NULL;

-- Note: membership_status column remains for backward compatibility during transition
-- It will be computed/derived from org lists when reading, but still written on updates
-- to maintain compatibility with existing code until all consumers are migrated
