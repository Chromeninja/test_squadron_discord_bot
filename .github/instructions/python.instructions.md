---
applyTo: "**/*.py"
description: "Python coding standards for this Discord bot project. Applied when editing any Python file. Covers type hints, datetime, logging, async patterns, imports, and data structures."
---

# Python Standards

## Type Hints — Required on ALL functions

Every function and method MUST have full type annotations (parameters + return type). Use `str | None` union syntax (Python 3.11+), not `Optional[str]`.

```python
async def get_member(user_id: int, guild_id: int) -> str | None: ...
```

## Datetime — Always timezone-aware

```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc)  # ✅ CORRECT
# datetime.utcnow()  ← FORBIDDEN (Ruff DTZ003)
```

## Logging — Never use `print()`

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Processing member %s", member_id)
logger.exception("Failed for %s", member_id, exc_info=e)
# print(...)  ← FORBIDDEN in production code
```

## Async Patterns

- Use `asyncio.gather()` or `asyncio.TaskGroup` for concurrent I/O
- Never use synchronous blocking calls (requests, sqlite3) in async code
- Use `aiohttp` for HTTP, `aiosqlite` for database

```python
# Concurrent I/O
results = await asyncio.gather(fetch_a(), fetch_b(), fetch_c())

# TaskGroup (Python 3.11+)
async with asyncio.TaskGroup() as tg:
    task1 = tg.create_task(fetch_a())
    task2 = tg.create_task(fetch_b())
```

## Data Structures

Use `@dataclass(slots=True)` for all data structures:

```python
from dataclasses import dataclass

@dataclass(slots=True)
class VerificationResult:
    user_id: int
    handle: str
    is_valid: bool
    message: str = ""
```

## Path Handling

Use `pathlib.Path`, never `os.path`:

```python
from pathlib import Path
config_path = Path("config") / "config.yaml"
```

## Imports

Sorted by Ruff `I` rules (isort-compatible). Group order: stdlib → third-party → local.

## Error Handling

Use `logger.exception()` with context — never bare `except:` or `except Exception: pass`:

```python
try:
    await operation()
except Exception as e:
    logger.exception("Operation failed for %s", context_id, exc_info=e)
    return False
```

## Security

- No `eval()` / `exec()` — never
- No `shell=True` in subprocess calls
- No hardcoded secrets — use `os.environ[]` or `Config.get()`
- Parameterized SQL only — always use `?` placeholders
- Never log full tokens — mask as `tok_****1234`
