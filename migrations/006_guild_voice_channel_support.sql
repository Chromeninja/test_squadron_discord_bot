-- Migration 006: Guild Voice Channel Support (safe schema-only)

-- This migration creates the new guild-scoped schema for voice settings but
-- intentionally does NOT migrate legacy data or perform destructive operations.
-- Reason: legacy settings (e.g. `join_to_create_channel_ids`) may be multi-valued
-- or the repository may not have a `guilds` table. Copying rows blindly would
-- risk assigning rows to the wrong guild or aborting the migration.
--
-- Data migration should be performed by the running application in an
-- idempotent, per-guild manner. See docs or the application startup task for
-- an example migration routine.

BEGIN TRANSACTION;

-- Create the guild_settings table (no data populated here)
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (guild_id, key)
);

-- Create new guild-scoped tables. These are created but left empty. An
-- application-driven migration should read legacy rows, resolve the correct
-- guild_id and jtc_channel_id for each row, and then insert into these
-- tables in a controlled, logged, and idempotent way.

CREATE TABLE IF NOT EXISTS user_voice_channels_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    voice_channel_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
);

CREATE TABLE IF NOT EXISTS voice_cooldowns_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS channel_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_name TEXT,
    user_limit INTEGER DEFAULT 0,
    lock INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS channel_permissions_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    permission TEXT NOT NULL,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

CREATE TABLE IF NOT EXISTS channel_ptt_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    ptt_enabled INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    priority_enabled INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

CREATE TABLE IF NOT EXISTS channel_soundboard_settings_new (
    guild_id INTEGER NOT NULL,
    jtc_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    soundboard_enabled INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
);

-- IMPORTANT: Do NOT copy or drop legacy tables here. Use an application-level
-- migration that can interact with the Discord API to determine the correct
-- guild->JTC mappings, handle multi-valued legacy settings, and log any
-- ambiguity for manual resolution. Once the application migration has
-- completed and been validated, a follow-up SQL migration can move data from
-- the *_new tables into the canonical names and drop the legacy tables.

COMMIT;
