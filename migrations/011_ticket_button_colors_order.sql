-- Migration 011: Button colors and display order

ALTER TABLE ticket_channel_configs
    ADD COLUMN private_button_color TEXT DEFAULT NULL;

ALTER TABLE ticket_channel_configs
    ADD COLUMN public_button_color TEXT DEFAULT NULL;

ALTER TABLE ticket_channel_configs
    ADD COLUMN button_order TEXT NOT NULL DEFAULT 'private_first';

-- Track migration
INSERT OR IGNORE INTO schema_migrations (version) VALUES (11);
