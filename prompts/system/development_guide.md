---
category: "system"
context: "development_guide"
variables:
  - name: "component_name"
    type: "string"
    description: "Name of the component being developed/modified"
  - name: "change_type"
    type: "string"
    enum: ["feature", "bugfix", "refactor", "optimization"]
    description: "Type of change being made"
schemas:
  - "database_models.json#/verification_record"
  - "discord_events.json#/member"
ai_hints:
  - "This guide helps AI agents understand the codebase architecture"
  - "Follow the established patterns for consistency"
  - "Use type hints and defensive programming practices"
---

# AI Agent Development Guide

## 🏗️ Architecture Overview

### Core Components

1. **`bot.py`** - Main entry point and Discord client setup
2. **`cogs/`** - Discord.py command modules (verification, voice, admin)
3. **`helpers/`** - Utility modules for common functionality
4. **`config/`** - Configuration management
5. **`verification/`** - RSI verification logic
6. **`data/`** - Data models and database interfaces
7. **`prompts/`** - AI-friendly templates and schemas

### Key Architectural Principles

- **Separation of Concerns**: Each module has a single responsibility
- **Type Safety**: Use type hints for all function parameters and returns
- **Defensive Programming**: Handle errors gracefully with structured error reporting
- **AI Comprehension**: Structure code and documentation for AI analysis

---

## 🔧 Development Patterns

### Error Handling Pattern

```python
from helpers.defensive_retry import discord_retry
from helpers.structured_errors import report_error

@discord_retry
async def risky_discord_operation(member: discord.Member) -> bool:
    try:
        # Discord API operation here
        await member.edit(roles=[role])
        return True
    except Exception as e:
        report_error(
            error=e,
            component='role_management',
            context={
                'member_id': member.id,
                'guild_id': member.guild.id,
                'operation': 'edit_roles'
            },
            severity='error'
        )
        return False
```

### Database Access Pattern

```python
import json
from helpers.database import Database

async def update_verification_status(
    user_id: int, 
    rsi_handle: str, 
    payload: dict
) -> bool:
    """Update verification payload with proper error handling (status derived from org lists)."""
    try:
        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE verification SET verification_payload = ?, last_updated = ? WHERE user_id = ?",
                (json.dumps(payload), int(time.time()), user_id)
            )
            await db.commit()
        return True
    except Exception as e:
        report_error(
            error=e,
            component='database',
            context={
                'operation': 'update_verification',
                'user_id': user_id,
                'rsi_handle': rsi_handle
            }
        )
        return False
```

### Type-Safe Configuration Access

```python
from config.config_loader import Config

def get_role_id(role_name: str) -> int | None:
    """Get role ID with type safety."""
    roles = Config.get('roles', {})
    role_id = roles.get(role_name)
    
    if role_id is None:
        logger.warning(f"Role '{role_name}' not configured")
        return None
    
    return int(role_id)
```

---

## 🧪 Testing Patterns

### Test Structure

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_verification_success(temp_db, monkeypatch) -> None:
    """Test successful verification flow."""
    # Arrange
    bot = MagicMock()
    member = MagicMock()
    member.id = 12345
    
    # Mock external dependencies
    monkeypatch.setattr("verification.rsi_verification.is_valid_rsi_handle", 
                       AsyncMock(return_value=(1, "TestHandle", "TestMoniker")))
    
    # Act
    result = await verify_member(bot, member, "TestHandle")
    
    # Assert
    assert result is True
    # Verify database state
    async with Database.get_connection() as db:
        cursor = await db.execute(
            "SELECT main_orgs FROM verification WHERE user_id = ?",
            (12345,)
        )
        row = await cursor.fetchone()
        main_orgs = json.loads(row[0]) if row and row[0] else []
        assert main_orgs  # User was marked as a member of at least one org
```

### Mock Discord Objects

```python
class FakeMember:
    def __init__(self, user_id: int, name: str, guild, roles=None, nick=None):
        self.id = user_id
        self.display_name = name
        self.guild = guild
        self.roles = roles or []
        self.nick = nick
        self.mention = f"<@{user_id}>"
    
    async def edit(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
```

---

## 🎯 AI-Specific Guidelines

### Code Documentation for AI

```python
def process_verification_result(
    member: discord.Member,
    verification_data: tuple[int, str | None, str | None]
) -> dict[str, Any]:
    """
    Process RSI verification result and determine member status.
    
    Args:
        member: Discord member object
        verification_data: Tuple of (status_code, cased_handle, moniker)
                          where status_code: 0=invalid, 1=main, 2=affiliate
    
    Returns:
        Dict containing:
        - success: bool
        - status: str ("main" | "affiliate" | "invalid")
        - roles_to_add: list[str]
        - roles_to_remove: list[str]
    
    AI Notes:
        - Status codes map to membership levels
        - Main members get full access, affiliates get limited access
        - Invalid results should not change existing roles
    """
    status_code, cased_handle, moniker = verification_data
    
    # Implementation here...
```

### Structured Data for AI Analysis

```python
@dataclass
class VerificationContext:
    """Context data for verification operations."""
    user_id: int
    guild_id: int
    rsi_handle: str
    initiator: str  # "user" | "admin" | "system"
    timestamp: datetime
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for AI analysis."""
        return {
            'user_id': self.user_id,
            'guild_id': self.guild_id,
            'rsi_handle': self.rsi_handle,
            'initiator': self.initiator,
            'timestamp': self.timestamp.isoformat(),
            'ai_context': {
                'operation_type': 'verification',
                'critical_path': True,
                'user_facing': True
            }
        }
```

---

## 🚀 Performance Guidelines

### Async Best Practices

```python
# Good: Concurrent operations
async def batch_verify_members(members: list[discord.Member]) -> list[bool]:
    """Verify multiple members concurrently."""
    tasks = [verify_single_member(member) for member in members]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions
    success_results = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Batch verification error: {result}")
            success_results.append(False)
        else:
            success_results.append(result)
    
    return success_results

# Bad: Sequential operations
async def slow_batch_verify(members: list[discord.Member]) -> list[bool]:
    """Don't do this - sequential verification is slow."""
    results = []
    for member in members:
        result = await verify_single_member(member)
        results.append(result)
    return results
```

### Database Optimization

```python
# Good: Batch operations
async def update_multiple_statuses(updates: list[tuple[str, int]]) -> None:
    """Update multiple verification statuses efficiently."""
    async with Database.get_connection() as db:
        await db.executemany(
            "UPDATE verification SET membership_status = ? WHERE user_id = ?",
            updates
        )
        await db.commit()

# Good: Single transaction for related operations
async def complete_verification(user_id: int, data: VerificationData) -> None:
    """Complete verification in a single transaction."""
    async with Database.get_connection() as db:
        # Update verification record
        await db.execute(
            "UPDATE verification SET membership_status = ?, rsi_handle = ?, last_updated = ?",
            (data.status, data.handle, int(time.time()))
        )
        
        # Add log entry
        await db.execute(
            "INSERT INTO verification_log (user_id, action, timestamp) VALUES (?, ?, ?)",
            (user_id, 'verified', int(time.time()))
        )
        
        await db.commit()
```

---

## 🔍 Debugging for AI Agents

### Structured Logging

```python
import structlog

logger = structlog.get_logger(__name__)

async def verify_member_with_logging(member: discord.Member, handle: str) -> bool:
    """Verification with structured logging for AI analysis."""
    log = logger.bind(
        operation="verify_member",
        user_id=member.id,
        guild_id=member.guild.id,
        rsi_handle=handle
    )
    
    log.info("Starting verification")
    
    try:
        result = await perform_verification(handle)
        log.info("Verification completed", result=result)
        return True
        
    except Exception as e:
        log.error("Verification failed", error=str(e), error_type=type(e).__name__)
        return False
```

### AI-Readable Error Context

```python
def create_error_context(
    operation: str,
    inputs: dict[str, Any],
    state: dict[str, Any]
) -> dict[str, Any]:
    """Create standardized error context for AI analysis."""
    return {
        'operation': operation,
        'inputs': inputs,
        'system_state': state,
        'timestamp': datetime.utcnow().isoformat(),
        'ai_debug_hints': [
            f"Operation '{operation}' failed with given inputs",
            "Check input validation and external service availability",
            "Review system state for any inconsistencies"
        ]
    }
```
