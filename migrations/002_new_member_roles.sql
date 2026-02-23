-- Migration 002: New-member role tracking table
-- Tracks temporary "new member" role assignments given on first verification.
-- The role is auto-removed after a configured number of days or when removed manually.
--
-- NOTE: The canonical DDL lives in services/db/schema.py and is applied on every
-- bot start-up via ensure_schema().  This migration file exists for auditability
-- and for manual/sequential migration tooling.  Keep both copies in sync.

CREATE TABLE IF NOT EXISTS new_member_roles (
    guild_id       INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    role_id        INTEGER NOT NULL,
    assigned_at    INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    expires_at     INTEGER NOT NULL,
    removed_at     INTEGER DEFAULT NULL,
    removed_reason TEXT    DEFAULT NULL,   -- 'expired', 'manual', 'disabled'
    active         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_new_member_roles_active ON new_member_roles(active, expires_at);
CREATE INDEX IF NOT EXISTS idx_new_member_roles_guild  ON new_member_roles(guild_id);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (2, strftime('%s','now'));
