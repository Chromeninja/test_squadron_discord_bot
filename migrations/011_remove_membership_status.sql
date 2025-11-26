-- Migration: Remove membership_status column from verification table
-- Date: 2025-11-26
-- Description: Removes the membership_status column as status is now derived dynamically
--              from main_orgs and affiliate_orgs columns per guild. This enables proper
--              multi-guild support where a user can have different statuses in different
--              guilds based on their organization memberships and each guild's tracked org.

-- Drop membership_status column - status is now derived from org lists per guild
ALTER TABLE verification DROP COLUMN membership_status;

-- Note: Status derivation logic is implemented in services/db/database.py::derive_membership_status()
-- which checks if the guild's tracked organization SID appears in the user's main_orgs or
-- affiliate_orgs lists to determine their status for that specific guild.
