# VS Code Workspace Configuration

This folder contains VS Code workspace settings tuned for automated test runs and AI agents.

## Python Environment

- **Virtual Environment**: `${workspaceFolder}/.venv/bin/python`
- All tests and tools use this venv to ensure consistency
- The venv is automatically added to PATH in integrated terminals

## Running Tests

### ⚠️ CRITICAL: Always run from workspace root with the venv!

**CORRECT ways to run tests:**
```bash
# From workspace root (recommended)
cd /home/chrome/test_squadron_discord_bot
.venv/bin/python -m pytest tests/                    # Bot tests
.venv/bin/python -m pytest web/backend/tests/        # Backend API tests
.venv/bin/python -m pytest tests/ web/backend/tests/ # All tests
```

**Or use VS Code tasks:**
- Press `Cmd+Shift+P` (or `Ctrl+Shift+P`)
- Type "Tasks: Run Task"
- Choose from:
  - `pytest: bot tests` - Run all bot tests (default)
  - `pytest: backend tests` - Run all backend API tests
  - `pytest: all tests` - Run everything
  - `pytest: bot tests (quick)` - Quiet mode for bot
  - `pytest: backend tests (quick)` - Quiet mode for backend

**WRONG ways (will fail):**
```bash
# ❌ DON'T: python or python3 directly (no pytest installed)
python -m pytest tests/
python3 -m pytest tests/

# ❌ DON'T: cd into subdirectory before running
cd web/backend && python3 -m pytest tests/

# ❌ DON'T: Run from wrong directory
cd web/backend
pytest tests/
```

## Test Configuration

- **pytest enabled**: Discovers tests automatically on save
- **Test discovery**: Looks for `test_*.py` and `*_test.py` files
- **Default working directory**: Workspace root
- **pytest binary**: `${workspaceFolder}/.venv/bin/pytest`

## Why This Matters

The bot and backend have separate `conftest.py` files that conflict if pytest's discovery includes both. Running from workspace root with explicit paths (`tests/` or `web/backend/tests/`) prevents this issue.

## Environment Setup

If your venv is named differently, update:
1. `.vscode/settings.json` - `python.defaultInterpreterPath`
2. `.vscode/tasks.json` - All task `command` paths
3. `.env` - Any environment-specific paths
