---
applyTo: "tests/**"
description: "Testing standards for pytest test files. Applied when editing test code. Covers Arrange/Act/Assert, async tests, fixtures, mocking, and forbidden patterns."
---

# Testing Standards

## Every new function/feature MUST have tests — no exceptions.

## Pattern — Arrange / Act / Assert

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

## Async Tests

- Use `@pytest.mark.asyncio` decorator on all async test functions
- Use `async def test_...` — never mix sync test with async code
- asyncio mode is `strict` with `function` scope (configured in `pyproject.toml`)

## Fixtures

- `temp_db` — in-memory database for database tests
- `mock_bot` — mock bot instance for Discord-dependent tests
- Use `monkeypatch.setattr()` for external dependencies

## Mocking Rules

- **All RSI/Discord API calls MUST be mocked** — no real network calls in tests
- Use `monkeypatch.setattr()` or `unittest.mock.AsyncMock` for async functions
- Mock at the boundary (where external calls happen), not deep internals

## Type Hints on Tests

All test functions MUST have a return type annotation of `-> None`:

```python
async def test_example(temp_db) -> None: ...
def test_sync_example() -> None: ...
```

## Forbidden Patterns

- ❌ Never comment out failing tests to make CI pass — fix them
- ❌ Never ignore pre-existing test failures — "it was already broken" is not acceptable
- ❌ Never make real API/network calls — mock everything external
- ❌ Never use `time.sleep()` — use `asyncio.sleep()` or mock time
- ❌ Never hardcode secrets in test data — use fake values

## Running Tests

```bash
pytest tests/ -v              # Bot tests
pytest web/backend/tests/ -v  # Backend API tests
pytest tests/ -q              # Quick mode
```
