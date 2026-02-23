# Copilot Instructions — TEST Squadron Discord Bot

## Project Overview

A Discord bot for managing TEST Squadron Star Citizen community — RSI profile verification, voice channels, role management, metrics tracking. Built with discord.py, aiosqlite, aiohttp, FastAPI (web dashboard).

**Python 3.11+ required.** Always target 3.11 syntax and features.

## Architecture

- `bot.py` / `bot.pyi` — Main bot class (`MyBot`). See `.pyi` stub for exact attribute types.
- `cogs/` — Discord.py command modules (admin, info, metrics, verification, voice)
- `helpers/` — Utility modules (reusable logic, no Discord state)
- `services/` — Business logic layer and database access (`services/db/`)
- `config/` — YAML-based configuration via `Config.get()`
- `verification/` — RSI profile verification logic
- `web/backend/` — FastAPI dashboard API
- `prompts/` — AI agent context docs & JSON schemas (read `prompts/system/development_guide.md` for full patterns)

## Critical Rules

### Datetime — NEVER use `datetime.utcnow()`

```python
# CORRECT — always timezone-aware
from datetime import datetime, timezone
now = datetime.now(timezone.utc)

# WRONG — Ruff DTZ003 will reject this
now = datetime.utcnow()  # ← FORBIDDEN
```

### Type Hints — Required on ALL functions

```python
# CORRECT
async def get_member_status(user_id: int, guild_id: int) -> str | None:
    ...

# WRONG — missing return type
async def get_member_status(user_id, guild_id):
    ...
```

### Error Handling — Use `logger.exception()` with context

```python
import logging
logger = logging.getLogger(__name__)

async def risky_operation(member_id: int) -> bool:
    try:
        await do_thing()
        return True
    except Exception as e:
        logger.exception(
            "Failed to process member %s",
            member_id,
            exc_info=e,
        )
        return False
```

### Database — Async context manager, single-transaction commits

```python
from services.db.database import Database

async def update_record(user_id: int, data: str) -> bool:
    try:
        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE verification SET data = ? WHERE user_id = ?",
                (data, user_id),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.exception("DB update failed for user %s", user_id, exc_info=e)
        return False
```

### Config Access — Type-safe via `Config.get()`

```python
from config.config_loader import Config

role_id: int | None = Config.get("roles", {}).get("member")
```

## Testing Requirements

- **Every new function/feature MUST have tests.** No exceptions.
- **Pattern:** Arrange / Act / Assert
- **Async tests:** Use `@pytest.mark.asyncio` + `async def test_...`
- **Fixtures:** Use `temp_db` for database tests, `mock_bot` for bot instance
- **Mocking:** Use `monkeypatch.setattr()` for external dependencies
- **No real API calls:** All RSI/Discord calls must be mocked
- Run tests: `pytest tests/ -v` (bot) or `pytest web/backend/tests/ -v` (backend)

```python
@pytest.mark.asyncio
async def test_update_record_success(temp_db, monkeypatch) -> None:
    """Test successful record update."""
    # Arrange
    user_id = 12345
    await seed_test_data(user_id)

    # Act
    result = await update_record(user_id, "new_data")

    # Assert
    assert result is True
```

## Code Style

- **Formatter/Linter:** Ruff (config in `pyproject.toml`) — runs via pre-commit
- **Type checker:** mypy strict mode (config in `pyproject.toml` `[tool.mypy]`)
- **Line length:** 88 characters
- **Imports:** Sorted by isort (via Ruff `I` rules)
- **Docstrings:** Include `AI Notes:` section for non-obvious logic
- **Security:** Ruff `S` (bandit) rules are enabled — no hardcoded secrets, no `eval()`, no `shell=True`

## Forbidden Patterns

- `datetime.utcnow()` → use `datetime.now(timezone.utc)`
- `print()` in production code → use `logger.info/debug/warning/error`
- Raw SQL without parameterized queries → always use `?` placeholders
- `eval()` / `exec()` → never
- Synchronous blocking calls in async code → use `aiohttp`, `aiosqlite`
- `os.path` → prefer `pathlib.Path`

## File Context

- Read `prompts/system/development_guide.md` for comprehensive architecture patterns
- Read `prompts/schemas/*.json` for database, Discord, and API data schemas
- Read `bot.pyi` for exact `MyBot` class attribute types
- Read `.vscode/README.md` for test execution guidance
