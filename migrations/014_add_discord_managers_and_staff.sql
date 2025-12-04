-- Migration: Add discord_managers, moderators, and staff role keys
-- Date: 2025-12-02
-- Description: Adds new permission role types to support 6-tier role hierarchy.
--              This migration creates placeholder entries for new role types while
--              preserving backward compatibility with existing lead_moderators.
--              
--              Role hierarchy: Bot Owner → Bot Admin → Discord Manager → Moderator → Staff → User
--
--              Note: This migration does NOT delete roles.lead_moderators to maintain
--              backward compatibility. Use the Python migration script to copy
--              lead_moderators to moderators after deployment.

-- No schema changes needed - guild_settings table already supports arbitrary key-value pairs.
-- This migration exists to document the new role keys being introduced.

-- New role keys introduced by this migration:
-- - roles.discord_managers: Users who can reset verification, manage voice, view all users
-- - roles.moderators: Users with read-only access to user/voice info (replaces lead_moderators)
-- - roles.staff: Users with basic staff privileges

-- Note: Initial values will be empty arrays. Use web admin UI or migration script to populate.
