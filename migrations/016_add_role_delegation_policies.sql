-- Migration: Add roles.delegation_policies guild setting
-- Date: 2025-12-05
-- Description: Introduces delegation policy storage for role grants. Policies are
--              stored as JSON under the key roles.delegation_policies. This
--              migration backfills an empty list for all existing guilds to keep
--              downstream code paths consistent. The operation is idempotent.

INSERT OR IGNORE INTO guild_settings (guild_id, key, value)
SELECT DISTINCT guild_id, 'roles.delegation_policies', '[]'
FROM guild_settings;

-- Touch settings version for cache invalidation on guilds where we inserted a row
WITH inserted AS (
    SELECT guild_id
    FROM guild_settings
    WHERE key = 'roles.delegation_policies'
)
INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
SELECT guild_id, 'meta.settings_version', json_object('version', strftime('%Y-%m-%dT%H:%M:%SZ','now'), 'source', 'role_delegation')
FROM inserted;
