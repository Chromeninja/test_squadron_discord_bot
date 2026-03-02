-- Migration 003: Ticketing System
--
-- Adds tables for a thread-based ticketing system:
--   * ticket_categories – per-guild categories (dropdown choices)
--   * tickets           – one row per opened ticket thread
--
-- Canonical DDL lives in services/db/schema.py; this file exists for
-- auditability and manual application if needed.

CREATE TABLE IF NOT EXISTS ticket_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL DEFAULT 0,
    name        TEXT    NOT NULL,
    description TEXT    DEFAULT '',
    welcome_message TEXT DEFAULT '',
    role_ids    TEXT    DEFAULT '[]',
    emoji       TEXT    DEFAULT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_ticket_categories_guild ON ticket_categories(guild_id);
CREATE INDEX IF NOT EXISTS idx_ticket_categories_guild_channel ON ticket_categories(guild_id, channel_id);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    thread_id   INTEGER NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    category_id INTEGER DEFAULT NULL REFERENCES ticket_categories(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    closed_by   INTEGER DEFAULT NULL,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    closed_at   INTEGER DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_guild_user_status ON tickets(guild_id, user_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_thread ON tickets(thread_id);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (3);
