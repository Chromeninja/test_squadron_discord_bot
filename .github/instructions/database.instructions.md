---
applyTo: "services/db/**"
description: "Database access patterns for aiosqlite. Applied when editing database service files. Covers async context managers, parameterized queries, transactions, and error handling."
---

# Database Standards

## Connection Pattern — Async context manager

Always use `Database.get_connection()` as an async context manager. Never hold connections outside `async with` blocks.

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

## Parameterized Queries — Always use `?` placeholders

**NEVER** use f-strings, `.format()`, or string concatenation in SQL:

```python
# ✅ CORRECT
await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))

# ❌ FORBIDDEN — SQL injection risk
await db.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

## Transactions — Single-transaction commits

- One `await db.commit()` per logical operation
- Keep transactions short — don't hold locks across I/O
- On error, the context manager handles rollback

## Batch Operations

For multiple related writes, use a single transaction:

```python
async with Database.get_connection() as db:
    for record in records:
        await db.execute(
            "INSERT INTO audit_log (user_id, action) VALUES (?, ?)",
            (record.user_id, record.action),
        )
    await db.commit()  # Single commit for all inserts
```

## Return Types

Database functions should return explicit types: `bool` for success/failure, `list[Row]` for queries, `int` for counts, `None | T` for single-record lookups.
