# Voice Setup Stale JTC Cleanup Implementation

## Overview
Enhanced the `/voice setup` command to automatically clean up stale Join-to-Create (JTC) data when the JTC channel configuration changes. This prevents old JTC associations from lingering in the database when channels are reconfigured.

## Implementation Details

### Database Utility: `Database.purge_stale_jtc_data()`
**Location**: `services/db/database.py`

```python
async def purge_stale_jtc_data(cls, guild_id: int, stale_jtc_ids: set[int]) -> dict[str, int]
```

**Features**:
- **Classmethod**: Properly implemented as a static database operation
- **Transactional**: Uses single transaction for all deletions with rollback on failure
- **Guild-scoped**: Only deletes data for the specified guild
- **JTC-filtered**: Only removes data associated with specific stale JTC channel IDs
- **Comprehensive**: Covers all 6 voice-related tables:
  - `user_voice_channels` - Active voice channel mappings
  - `channel_settings` - User channel preferences (name, limit, lock)
  - `channel_permissions` - Permit/reject settings per user/role/everyone
  - `channel_ptt_settings` - Push-to-talk permissions
  - `channel_priority_speaker_settings` - Priority speaker permissions  
  - `channel_soundboard_settings` - Soundboard permissions
- **Schema-aware**: Checks for column existence before attempting deletions
- **Return**: Dict mapping table names to number of rows deleted

### Service Helper: `VoiceService.cleanup_stale_jtc_managed_channels()`
**Location**: `services/voice_service.py`

```python
async def cleanup_stale_jtc_managed_channels(self, guild_id: int, stale_jtc_ids: set[int]) -> dict[str, Any]
```

**Features**:
- **Smart Channel Detection**: Finds managed voice channels belonging to stale JTC IDs
- **Safe Deletion**: Only deletes empty channels (no non-bot members)
- **Discord API Safe**: Handles NotFound/Forbidden errors gracefully
- **Cache Management**: Automatically removes deleted channels from managed channels cache
- **Detailed Reporting**: Returns comprehensive statistics about deletions and failures
- **Logging**: Extensive logging for troubleshooting and audit trails

### Enhanced Voice Setup Flow: `VoiceService.setup_voice_system()`
**Location**: `services/voice_service.py`

**New Workflow**:
1. **Capture Old Config**: Get current JTC channels before making changes
2. **Create New Channels**: Create requested number of JTC channels
3. **Compute Stale IDs**: Calculate `old_jtc_ids - new_jtc_ids`
4. **Cleanup Managed Channels**: Safely delete empty managed channels from stale JTCs
5. **Purge Database**: Remove all stale JTC associations from database
6. **Update Configuration**: Replace old JTC list with new channels
7. **Comprehensive Logging**: Log all operations with detailed statistics

## Safety Features

### Database Safety
- **Transactional Operations**: All database changes use transactions with rollback
- **Guild Scoping**: All operations are scoped to prevent cross-guild data loss
- **Schema Validation**: Checks for column existence before operations
- **Error Handling**: Comprehensive exception handling with detailed logging

### Discord API Safety  
- **Permission Handling**: Gracefully handles Discord API permission errors
- **Member Verification**: Only deletes channels with no non-bot members
- **Error Recovery**: Continues operation even if individual channel deletions fail
- **Cache Consistency**: Ensures cache stays synchronized with actual Discord state

### Data Integrity
- **Idempotent Operations**: Safe to run multiple times
- **Selective Deletion**: Only removes data associated with stale JTC IDs
- **Comprehensive Coverage**: Handles all voice-related database tables

## Logging & Monitoring

### Administrative Logs
- **Setup Summary**: Logs counts of created channels, stale JTCs, purged rows, deleted channels
- **Cleanup Details**: Individual channel deletion results with reasons
- **Error Tracking**: Exception details for troubleshooting
- **Audit Trail**: Admin actions with user IDs and timestamps

### Example Log Output
```
INFO: Current JTC channels for guild 123456: [111, 222]
INFO: Created JTC channel 333 (Join to Create)
INFO: New JTC channels: {333}
INFO: Stale JTC channels to clean up: {111, 222}
INFO: Deleted empty managed channel 555 for stale JTC 111
INFO: Stale JTC cleanup completed - Purged: {'channel_settings': 5, 'channel_permissions': 12}, Channels: {'deleted_channels': [{'voice_channel_id': 555, 'jtc_channel_id': 111}]}
INFO: Voice system setup complete for guild 123456: Created 1 JTC channels, Removed 2 stale JTC IDs, Purged 17 database rows, Deleted 1 empty channels, Failed to delete 0 channels
```

## Configuration Impact

### Before Implementation
- JTC channels were only added, never removed
- Old JTC associations persisted indefinitely in database
- Stale managed channels remained active
- Database grew with unused data over time

### After Implementation  
- JTC configuration completely replaces old configuration
- Stale data automatically cleaned up during setup
- Empty managed channels safely removed
- Database stays clean and relevant

## Error Handling

### Database Errors
- **Transaction Rollback**: Automatic rollback on database errors
- **Partial Failure**: Continues with cleanup even if some operations fail
- **Error Logging**: Detailed exception information for debugging

### Discord API Errors
- **Permission Errors**: Logged as warnings, operation continues
- **Missing Channels**: Automatic cache cleanup for missing channels
- **Rate Limiting**: Inherits Discord.py's built-in rate limiting

### Edge Cases
- **Empty Stale Set**: No-op when no stale JTC IDs exist
- **Missing Columns**: Schema validation prevents SQL errors
- **Channels with Users**: Skips deletion, logs warning with member count

## Testing Results
- ✅ Bot starts successfully with all changes
- ✅ All syntax checks pass  
- ✅ Method signatures properly typed
- ✅ Database transactions work correctly
- ✅ Voice setup command enhanced successfully

## Files Modified
1. **`services/db/database.py`** - Added `purge_stale_jtc_data()` classmethod
2. **`services/voice_service.py`** - Added `cleanup_stale_jtc_managed_channels()` and enhanced `setup_voice_system()`
3. **`cogs/voice/commands.py`** - Enhanced setup command feedback

## Benefits
- **Data Hygiene**: Prevents accumulation of stale voice data
- **Performance**: Reduces database bloat and query overhead  
- **Reliability**: Eliminates confusion from orphaned channel associations
- **Maintainability**: Automatic cleanup reduces manual administration
- **Transparency**: Comprehensive logging for administrators

The implementation ensures that when admins reconfigure JTC channels, the system automatically cleans up old associations while preserving active user data, maintaining database integrity and performance.