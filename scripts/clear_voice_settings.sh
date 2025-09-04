#!/usr/bin/env bash
# scripts/clear_voice_settings.sh
# Safely remove all current voice-related settings from an SQLite DB.
# Usage:
#   ./scripts/clear_voice_settings.sh [DB_PATH] [--yes]
# Defaults to TESTDatabase.db in repo root.
# The script will create a timestamped backup before modifying the DB.

set -euo pipefail

DB_PATH=${1:-TESTDatabase.db}
FORCE=false
if [[ ${2:-} == "--yes" || ${3:-} == "--yes" ]]; then
  FORCE=true
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: DB file not found: $DB_PATH"
  exit 2
fi

BACKUP="${DB_PATH}.bak.$(date +%s)"
cp "$DB_PATH" "$BACKUP"
echo "Backup created: $BACKUP"

if [[ "$FORCE" != "true" ]]; then
  echo "This will permanently DELETE all voice-related settings from: $DB_PATH"
  read -p "Type 'YES' to continue: " CONFIRM
  if [[ "$CONFIRM" != "YES" ]]; then
    echo "Aborted by user. No changes made."
    exit 0
  fi
fi

# Run SQL to clear voice tables and ensure guild_settings exists.
sqlite3 "$DB_PATH" <<'SQL'
BEGIN TRANSACTION;

-- Delete all rows from voice-related tables (idempotent)
DELETE FROM channel_settings;
DELETE FROM channel_permissions;
DELETE FROM channel_ptt_settings;
DELETE FROM channel_priority_speaker_settings;
DELETE FROM channel_soundboard_settings;
DELETE FROM user_voice_channels;
DELETE FROM voice_cooldowns;

-- Ensure the per-guild settings table exists (new schema)
CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY (guild_id, key)
);

COMMIT;
SQL

# Optional: reclaim space
sqlite3 "$DB_PATH" "VACUUM;"

echo "Voice settings cleared from $DB_PATH (backup at $BACKUP)."

echo "Next: deploy code, then restart the bot so Database.initialize() can create any missing tables and schema."

exit 0
