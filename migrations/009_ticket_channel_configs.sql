-- Migration 009: Add ticket_channel_configs table for per-channel panel customization

CREATE TABLE IF NOT EXISTS ticket_channel_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    panel_title TEXT NOT NULL DEFAULT '🎫 Support Tickets',
    panel_description TEXT NOT NULL DEFAULT 'Need help? Click the button below to open a support ticket.\n\nA private thread will be created for you and a staff member will assist you as soon as possible.',
    panel_color TEXT NOT NULL DEFAULT '0099FF',
    button_text TEXT NOT NULL DEFAULT 'Create Ticket',
    button_emoji TEXT DEFAULT '🎫',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(guild_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_ticket_channel_configs_guild 
    ON ticket_channel_configs(guild_id);

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (9);
