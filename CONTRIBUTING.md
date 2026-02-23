# Contributing to TEST Squadron Discord Bot

Thank you for contributing! This guide ensures consistent code quality whether you're writing code manually or with AI coding assistants (GitHub Copilot, etc.).

## Before You Start

1. Read the [project copilot instructions](.github/copilot-instructions.md) for coding conventions
2. Read [`prompts/system/development_guide.md`](prompts/system/development_guide.md) for architecture patterns
3. Set up your environment per [VS_CODE_SETUP.md](VS_CODE_SETUP.md)

## Development Workflow

### 1. Branch from `main`

```bash
git checkout main && git pull
git checkout -b feat/your-feature
```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

### 3. Write Code

Follow these rules — **enforced by pre-commit hooks and CI**:

| Rule | Enforcement |
|------|-------------|
| Type hints on all functions | mypy strict (`pyproject.toml`) |
| `datetime.now(timezone.utc)` not `utcnow()` | Ruff DTZ003 |
| No `print()` in production code | Ruff T20 |
| No `eval()` / `exec()` | Ruff S |
| Parameterized SQL (`?` placeholders) | Ruff S608 (advisory) + code review |
| Line length ≤ 88 chars | Ruff formatter |
| Imports sorted | Ruff I |

### 4. Write Tests

**Every new function/feature MUST have tests.** No exceptions.

```python
@pytest.mark.asyncio
async def test_your_feature(temp_db, monkeypatch) -> None:
    """Describe what this tests."""
    # Arrange
    ...

    # Act
    result = await your_function(...)

    # Assert
    assert result is True
```

- Use `temp_db` fixture for database tests
- Use `mock_bot` for bot instance tests
- Mock all external API calls (RSI, Discord)
- Run bot tests: `pytest tests/ -v`
- Run backend tests: `pytest web/backend/tests/ -v`

### 5. Validate Before Committing

```bash
# Pre-commit hooks run automatically, but you can also:
pre-commit run --all-files   # Lint + format + type check
pytest tests/ -v             # Run bot tests
pytest web/backend/tests/ -v # Run backend tests
```

### 6. Submit a Pull Request

- Target `main` branch
- Provide a clear description of what changed and why
- Ensure CI passes (tests + coverage ≥ 50%)
- Request review from a maintainer

## Code Style Quick Reference

- **Python 3.11+** syntax (use `X | Y` unions, not `Union[X, Y]`)
- **Ruff** for linting and formatting (config in `pyproject.toml`)
- **mypy strict** for type checking (config in `pyproject.toml`)
- **Docstrings** with `AI Notes:` section for non-obvious logic
- **Logging** via `logging.getLogger(__name__)` — use `logger.exception()` for errors
- **Database** via `async with Database.get_connection() as db:` — single-transaction commits
- **Config** via `Config.get("key", default)` — never hardcode values from config.yaml

## AI Coding Assistant Guidelines

If you use GitHub Copilot or other AI coding tools:

1. **Copilot auto-loads** [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for project context
2. **Review all AI-generated code** before committing — AI can miss project-specific patterns
3. **Run pre-commit hooks** — they catch common AI mistakes (wrong datetime, missing types, print statements)
4. **Always add tests** for AI-generated code — the coverage floor is enforced in CI
5. **Check `bot.pyi`** — type stub ensures AI uses correct attribute types on the bot class

## Forbidden Patterns

These will be caught by linting/CI:

- `datetime.utcnow()` → `datetime.now(timezone.utc)`
- `print()` → `logger.info()` / `logger.debug()`
- `eval()` / `exec()` → never
- `os.path` → `pathlib.Path`
- Raw SQL strings → parameterized queries with `?`
- Synchronous blocking in async code → `aiohttp`, `aiosqlite`

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.
