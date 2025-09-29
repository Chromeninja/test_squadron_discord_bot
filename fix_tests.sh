#!/bin/bash

# Fix test_voice_cleanup.py to use new schema

# Replace INSERT statements with proper new schema
sed -i -E 's/INSERT INTO voice_channels[[:space:]]*\(guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at\)[[:space:]]*VALUES \(\?, \?, \?, \?, \?\)/INSERT INTO voice_channels\n                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)\n                VALUES (?, ?, ?, ?, ?, ?, ?)/g' tests/test_voice_cleanup.py

# Update corresponding value tuples - this needs to be done for each specific case
# We'll need to add two more parameters: last_activity (same as created_at) and is_active (1)