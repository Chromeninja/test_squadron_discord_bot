-- Migration: Remove legacy lead_moderators role entries
-- Date: 2025-12-04
-- Description: Cleans up deprecated roles.lead_moderators guild settings now that
--              the permission system no longer supports legacy fallbacks.
--              The operation is idempotent and safe to run multiple times.

WITH affected_guilds AS (
    SELECT DISTINCT guild_id
    FROM guild_settings
    WHERE key = 'roles.lead_moderators'
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
    'MIGRATION_015_REMOVE_LEAD_MODERATORS',
    'Removed legacy lead_moderators role assignments',
    NULL,
    0,
    strftime('%s', 'now')
FROM affected_guilds;

DELETE FROM guild_settings WHERE key = 'roles.lead_moderators';
