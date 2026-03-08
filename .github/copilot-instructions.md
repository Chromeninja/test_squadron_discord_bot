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
- **PEP Compliance:** PEP 8 (style), PEP 257 (docstrings), PEP 484 (type hints)
- **Dataclasses:** Use `@dataclass(slots=True)` for all data structures (memory-efficient)
- **Async concurrency:** Use `asyncio.gather()` or `asyncio.TaskGroup` for concurrent I/O — never mix sync blocking calls in async code

## Forbidden Patterns

- `datetime.utcnow()` → use `datetime.now(timezone.utc)`
- `print()` in production code → use `logger.info/debug/warning/error`
- Raw SQL without parameterized queries → always use `?` placeholders
- `eval()` / `exec()` → never
- Synchronous blocking calls in async code → use `aiohttp`, `aiosqlite`
- `os.path` → prefer `pathlib.Path`
- Hardcoded secrets, API keys, tokens → use environment variables or `config.yaml`
- Logging full token/secret values → log only masked representations (e.g., `tok_****1234`)
- Passing secrets as CLI arguments → read from env vars, files, or stdin
- Commenting out failing tests to make CI pass → fix the tests
- `TODO` placeholders in committed code → implement fully or create a GitHub Issue
- `sudo` in automated commands → ask the user to run manually
- `--no-verify` to skip git hooks → never bypass pre-commit checks
- Ignoring pre-existing test failures → fix them, "it was already broken" is never acceptable

## Development Philosophy

**Safe, stable, and feature-complete — never take shortcuts.**

### Core Principles

- **No Quick Fixes:** Resist workarounds or partial solutions
- **Complete Features:** Fully implemented with proper error handling and validation
- **Safety First:** Security, data integrity, and fault tolerance are non-negotiable
- **Stable Foundations:** Build on solid, tested components
- **No Technical Debt:** Address issues properly the first time

### Red Flags (Never Do These)

- ❌ Skipping input validation "just this once"
- ❌ Hardcoding credentials or configuration values
- ❌ Ignoring error returns or exceptions
- ❌ Commenting out failing tests to make CI pass
- ❌ Using deprecated or unmaintained dependencies
- ❌ Implementing partial features with `TODO` placeholders
- ❌ Bypassing security checks for convenience
- ❌ Assuming data is valid without verification
- ❌ Leaving debug code in production paths
- ❌ Running `sudo` commands — ask the user to run them manually
- ❌ Printing or logging full secret/token values — log only masked representations

### Quality Checklist Before Completion

- ✅ All error cases handled properly
- ✅ Unit tests cover new code paths
- ✅ Security requirements implemented (no hardcoded secrets, input validated)
- ✅ Type hints on all functions, mypy passes
- ✅ Ruff lint and format checks pass
- ✅ Documentation/docstrings complete for public APIs
- ✅ No hardcoded secrets or credentials
- ✅ Logging in place for error paths
- ✅ Edge cases and boundary conditions tested

## Security Standards

### Input Validation (Mandatory)

- **ALL inputs** require validation before processing — Discord command arguments, API request bodies, user-submitted RSI handles
- SQL injection prevention: always use parameterized queries (`?` placeholders) with `aiosqlite`
- XSS prevention: escape user-provided content before embedding in Discord embeds or web responses
- Type checking and bounds validation on all external inputs

### Secrets & Credentials

- Store all secrets in environment variables or `config.yaml` (which is in `.gitignore`)
- **NEVER** commit secrets, API keys, Discord tokens, or credentials
- **NEVER** pass tokens as CLI arguments (they appear in shell history and `ps aux`)
- **NEVER** log full token/secret values — log only masked representations (e.g., `tok_****1234`)
- Read secrets from env vars in code: `os.environ["DISCORD_TOKEN"]`

### Security Scanning

Before committing dependency changes, run:
```bash
# Ruff bandit rules (security issue detection)
ruff check --select S .

# Dependency vulnerability check
pip-audit
```

**Do NOT commit if vulnerabilities are found** — fix all issues first.

### Verification Before Commit

```bash
# Scan staged changes for accidentally committed secrets
git diff --cached | grep -iE 'password|secret|key|token|credential|api_key'
```

Review any matches — false positives are common but must be verified.

## Git Workflow

### Core Rules

- **NEVER commit** unless explicitly requested by the user
- **NEVER push** to remote — only push when explicitly asked
- **NEVER ask about pushing** — do not suggest or prompt for git push
- **NEVER edit code directly on `main`** — always work on a feature branch
- **CHECK current branch** before any code change: if on `main`, create and switch to a feature branch first
- **Prefer `gh` CLI** over direct GitHub API calls for all GitHub operations
- **Never ignore pre-existing failures** — if tests were already failing before your changes, fix them

### Branch Naming

```
feat/<short-description>    # New features
fix/<short-description>     # Bug fixes
chore/<short-description>   # Maintenance, refactoring, dependency updates
```

### Pre-Commit Checklist

Run these checks before every commit (all must pass):

```bash
# 1. Lint
ruff check .

# 2. Format check
ruff format --check .

# 3. Type check
mypy .

# 4. Run tests
pytest tests/ -v

# 5. Security scan (if dependencies changed)
pip-audit

# 6. Secret detection
git diff --cached | grep -iE 'password|secret|key|token|credential|api_key'
```

**NEVER commit if any step fails.** Fix issues and re-run from step 1.

### PR Conventions

- Every PR body MUST contain `Closes #<issue-number>` to auto-close the linked issue
- PR title should reference the issue: `[Feature] Add verification timeout (#42)`
- Assign PR to the same person as the issue

## GitHub Issues

### Required Labels

Every issue MUST have at least one label from **type** and **priority**:

| Dimension | Values |
|-----------|--------|
| **Type** (one) | `type:feature` `type:bug` `type:chore` `type:docs` `type:security` |
| **Priority** (one) | `priority:critical` `priority:high` `priority:medium` `priority:low` |
| **Status** (update as work progresses) | `status:ready` `status:in-progress` `status:blocked` `status:review` |
| **Component** (one+) | `component:verification` `component:voice` `component:admin` `component:metrics` `component:tickets` `component:web-dashboard` `component:database` `component:config` `component:bot-core` |
| **Size** (optional) | `size:xs` `size:s` `size:m` `size:l` `size:xl` |

### Issue Body Template

```markdown
## User Story
As a [role], I want [capability] so that [benefit].

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests pass (unit + integration)
- [ ] Ruff lint passes
- [ ] mypy type check passes

## Notes
Any additional context, constraints, or references.
```

### Rules

- ✅ Auto-assign issue to creator (`--assignee @me`)
- ✅ Check for duplicates before creating (`gh issue list --search "..."`)
- ✅ Link every issue to a milestone before starting work
- ✅ Close issues via PR merge with `Closes #N` — never close manually
- ✅ Check if an issue is already assigned before claiming it
- ❌ Never create issues without labels (type + priority required)
- ❌ Never assign more than one person per issue

## File Context

- Read `prompts/system/development_guide.md` for comprehensive architecture patterns
- Read `prompts/schemas/*.json` for database, Discord, and API data schemas
- Read `bot.pyi` for exact `MyBot` class attribute types
- Read `.vscode/README.md` for test execution guidance
