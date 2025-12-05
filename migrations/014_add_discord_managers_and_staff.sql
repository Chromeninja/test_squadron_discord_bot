-- Migration: Add discord_managers, moderators, and staff role keys
-- Date: 2025-12-02
-- Description: Adds new permission role types to support 6-tier role hierarchy.
--              This migration creates placeholder entries for the new role types.
--
--              Role hierarchy: Bot Owner → Bot Admin → Discord Manager → Moderator → Staff → User
--
--              Note: Any legacy roles.lead_moderators entries should be cleaned up
--              with migration 015 once the new roles are populated.

-- No schema changes needed - guild_settings table already supports arbitrary key-value pairs.
-- This migration exists to document the new role keys being introduced.

-- New role keys introduced by this migration:
-- - roles.discord_managers: Users who can reset verification, manage voice, view all users
-- - roles.moderators: Users with read-only access to user/voice info
-- - roles.staff: Users with basic staff privileges

-- Note: Initial values will be empty arrays. Use web admin UI or migration script to populate.
