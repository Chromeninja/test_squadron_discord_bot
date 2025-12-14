# DRY Patterns & Utilities Reference

This document describes the unified patterns and utilities for the TEST Squadron Discord Bot codebase. Following these patterns ensures consistent, maintainable code.

## 1. Database Access (services/db/repository.py)

### BaseRepository

Use instead of direct `Database.get_connection()` patterns:

```python
from services.db import BaseRepository, repo

# Simple queries
row = await BaseRepository.fetch_one(
    "SELECT * FROM verification WHERE user_id = ?", (user_id,)
)

# Fetch all
rows = await BaseRepository.fetch_all(
    "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
)

# Single value
count = await BaseRepository.fetch_value(
    "SELECT COUNT(*) FROM verification", default=0
)

# Write operations
affected = await BaseRepository.execute(
    "UPDATE verification SET needs_reverify = 1 WHERE user_id = ?",
    (user_id,),
)

# Check existence
exists = await BaseRepository.exists(
    "SELECT 1 FROM verification WHERE user_id = ?", (user_id,)
)

# Transactions
async with BaseRepository.transaction() as db:
    await db.execute("INSERT ...", params1)
    await db.execute("UPDATE ...", params2)
    # Auto-commits on success, rolls back on exception
```

### JSON Parsing Utilities

```python
from services.db import parse_json_list, parse_json_dict, parse_org_lists

# Parse JSON safely
orgs = parse_json_list(row["main_orgs"])  # Returns [] if None/invalid
settings = parse_json_dict(row["settings"])  # Returns {} if None/invalid

# Parse org lists together
main_orgs, affiliate_orgs = parse_org_lists(main_json, affiliate_json)

# Derive membership status
status = derive_membership_status(main_orgs, affiliate_orgs, "TEST")
```

## 2. Web Backend Validation (web/backend/core/validation.py)

### ID Parsing

```python
from core.validation import (
    parse_snowflake_id,
    ensure_active_guild,
    ensure_guild_match,
    ensure_user_and_guild_ids,
)

# Parse with automatic HTTPException on failure
user_id = parse_snowflake_id(user_id_str, "User ID")

# Ensure active guild (raises 400 if not set)
guild_id = ensure_active_guild(current_user)

# Ensure guild matches active guild (raises 403 if mismatch)
guild_id = ensure_guild_match(requested_guild_id, current_user)

# Parse user ID and get guild ID together
user_id, guild_id = ensure_user_and_guild_ids(user_id_str, current_user)
```

### Error Handling Decorator

```python
from core.validation import api_error_handler

@router.get("/users/{user_id}")
@api_error_handler("Failed to fetch user")
async def get_user(user_id: str):
    # Exceptions automatically translated to HTTPException
    return await internal_api.get_user(user_id)
```

### Data Coercion

```python
from core.validation import safe_int, coerce_role_list, validate_pagination

role_id = safe_int(value)  # Returns None if invalid
role_ids = coerce_role_list(raw_roles)  # Cleans and deduplicates

page, per_page, offset = validate_pagination(page, per_page, max_per_page=100)
```

## 3. Discord Reply Helpers (helpers/discord_reply.py)

### Unified Response Helper (Preferred)

```python
from helpers.discord_reply import respond

# Text response
await respond(interaction, "✅ Done!", ephemeral=True)

# Embed response
await respond(interaction, embed=my_embed)

# With view
await respond(interaction, "Choose an option:", view=my_view)
```

### Specialized Helpers

```python
from helpers.discord_reply import (
    send_user_error,
    send_user_success,
    send_user_info,
    dm_user,
    dm_embed,
)

# Auto-adds emoji prefix if not present
await send_user_error(interaction, "User not found")  # Adds ❌
await send_user_success(interaction, "Saved!")  # Adds ✅

# DM helpers
await dm_user(member, "⚠️ Rate limit warning")
await dm_embed(member, info_embed)
```

## 4. Embed Factory (helpers/embeds.py)

### Standard Colors

```python
from helpers.embeds import EmbedColors

embed = discord.Embed(color=EmbedColors.SUCCESS)  # Green
embed = discord.Embed(color=EmbedColors.ERROR)    # Red
embed = discord.Embed(color=EmbedColors.WARNING)  # Orange
embed = discord.Embed(color=EmbedColors.INFO)     # Blue
embed = discord.Embed(color=EmbedColors.PRIMARY)  # Yellow (TEST branding)
embed = discord.Embed(color=EmbedColors.ADMIN)    # Red-ish (admin actions)
```

### Factory Functions

```python
from helpers.embeds import (
    create_info_embed,
    create_warning_embed,
    create_admin_embed,
    create_status_embed,
    create_list_embed,
)

# Informational embed
embed = create_info_embed(
    "Voice Settings",
    "Your current settings:",
    fields=[("Name", "My Channel", True), ("Limit", "10", True)],
)

# Admin action embed
embed = create_admin_embed(
    "User Reset",
    "Voice settings cleared",
    action_by="Admin#1234",
    target="User#5678",
)

# Status summary
embed = create_status_embed(
    "Bulk Operation Complete",
    success_items=["User 1", "User 2"],
    warning_items=["User 3 (partial)"],
    error_items=["User 4 (failed)"],
)
```

## 5. Permission Checking (helpers/permissions_helper.py)

### Unified Permission Check

```python
from helpers.permissions_helper import has_permission_level, PermissionLevel

# Single unified check (preferred for new code)
if await has_permission_level(bot, member, PermissionLevel.MODERATOR, guild):
    # User has moderator or higher permission

# Legacy functions still available for compatibility
from helpers.permissions_helper import is_bot_admin, is_moderator
```

### Permission Levels (hierarchy order)

```
USER = 1
STAFF = 2
MODERATOR = 3
DISCORD_MANAGER = 4
BOT_ADMIN = 5
BOT_OWNER = 6
```

## 6. Type-Safe Config Access (services/config_service.py)

```python
# Instead of raw get() with hardcoded keys:
org_sid = await config.get(guild_id, "organization.sid", default="TEST")

# Use typed accessors:
org_sid = await config.get_org_sid(guild_id)
verified_role = await config.get_verified_role_id(guild_id)
admin_roles = await config.get_bot_admin_role_ids(guild_id)
verification_channel = await config.get_verification_channel_id(guild_id)
```

## Best Practices Summary

1. **Database**: Use `BaseRepository` methods instead of direct connection patterns
2. **Validation**: Use `ensure_*` functions for consistent HTTPException handling
3. **Responses**: Use `respond()` for all interaction responses
4. **Embeds**: Use `EmbedColors` and factory functions for consistent styling
5. **Permissions**: Use `has_permission_level()` for new permission checks
6. **Config**: Use typed accessor methods for common config values

## Migration Notes

These utilities are additive - existing code continues to work. When modifying existing files, gradually migrate to the new patterns for consistency.
