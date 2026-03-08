---
name: pre-commit-checks
description: "Use before every git commit to run the full pre-commit validation sequence. Invoke when preparing code for committing, running pre-commit checks, or validating code quality before a commit."
---

# Running Pre-Commit Checks

## Overview

Six steps that must all pass before any commit. Run them in order — if any step fails, fix the issue and restart from step 1.

## When to Use

- Before every `git commit`
- When asked to "prepare for commit" or "run pre-commit"
- When validating that code is ready to commit

## Process

### Step 1: Lint

```bash
ruff check .
```

Fix all lint errors. Ruff enforces 40+ rule categories including security (S/bandit), datetime (DTZ), type checking (TCH), and style (E/W/F).

### Step 2: Format Check

```bash
ruff format --check .
```

If formatting issues are found, fix with `ruff format .` then re-run step 1.

### Step 3: Type Check

```bash
mypy .
```

All functions must have type hints. mypy runs in strict mode (configured in `pyproject.toml`).

### Step 4: Run Tests

```bash
pytest tests/ -v
```

All tests must pass. For backend tests: `pytest web/backend/tests/ -v`.

### Step 5: Security Scan (if dependencies changed)

```bash
pip-audit
```

Run when `requirements.txt` or `pyproject.toml` dependencies were modified. Do NOT commit if vulnerabilities are found.

### Step 6: Secret Detection

```bash
git diff --cached | grep -iE 'password|secret|key|token|credential|api_key'
```

Review any matches — false positives are common but must be verified. No hardcoded secrets allowed.

## Quick Reference

| Step | Check | Command | Blocker? |
|------|-------|---------|----------|
| 1 | Lint | `ruff check .` | Yes |
| 2 | Format | `ruff format --check .` | Yes |
| 3 | Type check | `mypy .` | Yes |
| 4 | Tests | `pytest tests/ -v` | Yes |
| 5 | Dependencies | `pip-audit` | If deps changed |
| 6 | Secrets | `git diff --cached \| grep ...` | Yes |

## Common Mistakes

- Running steps out of order — lint and format first, then type check, then tests
- Committing after a partial pass ("tests passed so I'll skip linting")
- Forgetting to re-run from step 1 after fixing issues
- Using `--no-verify` to skip git hooks — **never bypass pre-commit checks**

## Red Flags

- **NEVER** commit if any step fails
- **NEVER** use `--no-verify` to skip git hooks
- **ALWAYS** run the complete sequence, not a subset
- **ALWAYS** re-run from step 1 if you made code changes to fix issues
