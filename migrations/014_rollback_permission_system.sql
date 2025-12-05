-- Rollback: Remove discord_managers, moderators, and staff role keys
-- Date: 2025-12-02
-- Description: Rollback script to remove new permission role keys if upgrade fails.
--              This script deletes the new role entries and assumes migration 015 will
--              remove any legacy lead_moderators references if a full rollback is required.
--
--              WARNING: This will DELETE any discord_managers, moderators, and staff
--              role assignments. Ensure you have a database backup before rollback.

-- Audit the rollback before deleting the role assignments
WITH affected_guilds AS (
    SELECT DISTINCT guild_id
    FROM guild_settings
    WHERE key IN ('roles.discord_managers', 'roles.moderators', 'roles.staff')
)
INSERT INTO guild_settings_audit (
    guild_id,
    key,
    old_value,
    new_value,
    changed_by_user_id,
    changed_at
)
SELECT
    guild_id,
    'ROLLBACK_014',
    'Removed new permission role keys',
    NULL,
    0,
    strftime('%s', 'now')
FROM affected_guilds;

-- Remove new role keys from all guilds
DELETE FROM guild_settings WHERE key = 'roles.discord_managers';
DELETE FROM guild_settings WHERE key = 'roles.moderators';
DELETE FROM guild_settings WHERE key = 'roles.staff';
