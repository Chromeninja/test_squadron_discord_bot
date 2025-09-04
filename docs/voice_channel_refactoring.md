# Voice Channel System Refactoring Summary

## Overview

The voice channel system has been refactored to make settings and permissions unique per guild (server), per join-to-create channel, and per user. This enables the bot to support multiple Discord servers with independent voice channel configurations.

## Changes Made

### Database Schema

1. Added a new `guild_settings` table with columns:
   - `guild_id`: The Discord server ID
   - `key`: Setting name
   - `value`: Setting value

2. Modified existing voice-related tables to include `guild_id` and `jtc_channel_id`:
   - `user_voice_channels`
   - `voice_cooldowns`
   - `channel_settings`
   - `channel_permissions`
   - `channel_ptt_settings`
   - `channel_priority_speaker_settings`
   - `channel_soundboard_settings`

3. Created a migration file (006_guild_voice_channel_support.sql) for these changes.

### Voice Cog Modifications

1. Updated the cog initialization to use guild-specific dictionaries:
   - `guild_jtc_channels`: Maps guild IDs to join-to-create channel IDs
   - `guild_voice_categories`: Maps guild IDs to voice category IDs

2. Modified `cog_load()` to load settings from the new `guild_settings` table.

3. Enhanced the `/voice setup` command to store configurations per guild.

4. Updated `on_voice_state_update()` to check guild-specific join-to-create channels.

5. Modified cooldown checks and channel creation to use guild-specific settings.

6. Fixed `cleanup_stale_channel_data()` to use `timestamp` column instead of non-existent `last_created` column.

7. Enhanced admin commands:
   - `/voice admin_list` now displays all voice channel settings for a user in the current guild, organized by join-to-create channel
   - `/voice admin_reset` now accepts an optional join-to-create channel parameter to reset settings for a specific channel

### Helper Functions

1. Updated functions in `helpers/voice_utils.py`:
   - `get_user_channel()`: Added guild and JTC channel filtering
   - `update_channel_settings()`: Added guild and JTC channel parameters
   - `fetch_channel_settings()`: Added guild and JTC channel filtering
   - `set_voice_feature_setting()`: Added guild and JTC channel context
   - `_fetch_settings_table()`: Added guild and JTC channel parameters

2. Updated functions in `helpers/permissions_helper.py`:
   - `store_permit_reject_in_db()`: Added guild and JTC channel parameters
   - `fetch_permit_reject_entries()`: Added guild and JTC channel filtering
   - `update_channel_owner()`: Added guild and JTC channel context

3. Added guild and JTC channel support to channel reset functionality:
   - `_reset_current_channel_settings()` now supports three modes:
     - Reset settings for a specific user, guild, and JTC channel
     - Reset all settings for a user within a guild
     - Reset all settings for a user (legacy mode)

### UI Components

1. Updated modals in `helpers/modals.py`:
   - `NameModal`: Added guild and JTC channel parameters
   - `LimitModal`: Added guild and JTC channel parameters
   - `ResetSettingsConfirmationModal`: Added guild and JTC channel parameters

2. Updated views in `helpers/views.py`:
   - `ChannelSettingsView`: Modified to handle guild-specific context

## Backward Compatibility

The refactoring maintains backward compatibility:
- Legacy database queries are used as fallbacks when guild/JTC parameters aren't provided
- Original attributes (`join_to_create_channel_ids`, `voice_category_id`) are preserved for compatibility
- The bot will migrate existing settings to the new structure when needed

## Benefits

1. **Multi-Server Support**: The bot can now manage independent voice channels across multiple Discord servers.

2. **Per-Channel Customization**: Users can have different settings for each join-to-create channel.

3. **Isolated Permissions**: Channel permissions are now scoped by guild and join-to-create channel.

4. **Improved Flexibility**: Administrators can configure different voice channel setups for different parts of their server.

5. **Enhanced Admin Tools**: Admin commands now support operations specific to servers and JTC channels:
   - View all settings across multiple JTC channels
   - Reset settings for specific JTC channels

## Admin Commands Usage

### Viewing User Settings
```
/voice admin_list user:@username
```
This displays all saved channel settings for the user in the current server, organized by join-to-create channel.

### Resetting User Settings
```
/voice admin_reset user:@username [jtc_channel:#voice-channel]
```
- Without specifying a JTC channel: Resets all the user's voice settings in the current server
- With a specific JTC channel: Resets only the settings for that specific join-to-create channel

## Fallback Defaults

If no settings exist for a user in the current guild/JTC channel, the system falls back to:
- User's display name or game name for the channel name
- Unlimited user limit
- Unlocked state
- Empty permissions and features

## Deployment Instructions

When deploying to production, follow these steps:

1. Create a backup of your production database
2. Run the `scripts/clear_voice_settings.sh` script to clear voice settings and ensure tables exist:
   ```bash
   ./scripts/clear_voice_settings.sh /path/to/your/prod.db --yes
   ```
3. Deploy the updated code
4. Restart the bot to allow new tables to be created on initialization

This completes the refactoring of the dynamic voice channel system to support per-guild, per-JTC channel, and per-user settings and permissions.
