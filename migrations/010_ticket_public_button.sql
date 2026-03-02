-- Migration 010: Optional public ticket button per channel config

ALTER TABLE ticket_channel_configs
    ADD COLUMN enable_public_button INTEGER NOT NULL DEFAULT 0;

ALTER TABLE ticket_channel_configs
    ADD COLUMN public_button_text TEXT NOT NULL DEFAULT 'Create Public Ticket';

ALTER TABLE ticket_channel_configs
    ADD COLUMN public_button_emoji TEXT DEFAULT '🌐';

ALTER TABLE ticket_route_sessions
    ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0;

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (10);
