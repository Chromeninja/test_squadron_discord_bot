-- Metrics schema (version 1)
-- Applied to the SEPARATE metrics database (metrics.db), NOT the main bot DB.
-- All timestamps are Unix epoch seconds (INTEGER).

CREATE TABLE IF NOT EXISTS metrics_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at INTEGER DEFAULT (strftime('%s','now'))
);

INSERT OR IGNORE INTO metrics_schema_migrations (version, applied_at)
VALUES (1, strftime('%s','now'));

-- Voice Sessions: raw session log (join/leave per user)
CREATE TABLE IF NOT EXISTS voice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    joined_at INTEGER NOT NULL,
    left_at INTEGER,
    duration_seconds INTEGER
);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_user ON voice_sessions(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_joined ON voice_sessions(guild_id, joined_at);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_open ON voice_sessions(left_at) WHERE left_at IS NULL;

-- Game Sessions: raw activity/presence log
CREATE TABLE IF NOT EXISTS game_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game_name TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    duration_seconds INTEGER
);
CREATE INDEX IF NOT EXISTS idx_game_sessions_guild_user ON game_sessions(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_game_sessions_guild_started ON game_sessions(guild_id, started_at);
CREATE INDEX IF NOT EXISTS idx_game_sessions_game ON game_sessions(guild_id, game_name);
CREATE INDEX IF NOT EXISTS idx_game_sessions_open ON game_sessions(ended_at) WHERE ended_at IS NULL;

-- Message Counts: hourly bucketed message counters (upsert pattern)
CREATE TABLE IF NOT EXISTS message_counts (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    hour_bucket INTEGER NOT NULL,
    bucket_seconds INTEGER NOT NULL DEFAULT 3600,
    message_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, hour_bucket)
);
CREATE INDEX IF NOT EXISTS idx_message_counts_guild_hour ON message_counts(guild_id, hour_bucket);
CREATE INDEX IF NOT EXISTS idx_message_counts_guild_bucket_seconds ON message_counts(guild_id, bucket_seconds, hour_bucket);

-- Metrics Hourly: pre-aggregated server-wide rollups
CREATE TABLE IF NOT EXISTS metrics_hourly (
    guild_id INTEGER NOT NULL,
    hour_bucket INTEGER NOT NULL,
    total_messages INTEGER NOT NULL DEFAULT 0,
    unique_messagers INTEGER NOT NULL DEFAULT 0,
    total_voice_seconds INTEGER NOT NULL DEFAULT 0,
    unique_voice_users INTEGER NOT NULL DEFAULT 0,
    top_game TEXT,
    PRIMARY KEY (guild_id, hour_bucket)
);
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_guild_hour ON metrics_hourly(guild_id, hour_bucket);

-- Metrics User Hourly: pre-aggregated per-user rollups
CREATE TABLE IF NOT EXISTS metrics_user_hourly (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    hour_bucket INTEGER NOT NULL,
    messages_sent INTEGER NOT NULL DEFAULT 0,
    voice_seconds INTEGER NOT NULL DEFAULT 0,
    games_json TEXT,
    PRIMARY KEY (guild_id, user_id, hour_bucket)
);
CREATE INDEX IF NOT EXISTS idx_metrics_user_hourly_guild_hour ON metrics_user_hourly(guild_id, hour_bucket);
CREATE INDEX IF NOT EXISTS idx_metrics_user_hourly_user ON metrics_user_hourly(guild_id, user_id, hour_bucket);
