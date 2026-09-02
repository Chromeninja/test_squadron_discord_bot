# VS Code Workspace Configuration

This folder contains VS Code workspace settings tuned for automated test runs and AI agents.

## Python Environment

- **Virtual Environment**: `${workspaceFolder}/.venv`
- All tests and tools use this venv to ensure consistency
- The venv is automatically added to PATH in integrated terminals

## Running Tests

### ⚠️ CRITICAL: Always run from workspace root with the venv!

**CORRECT ways to run tests:**
```bash
# From workspace root (Linux/macOS)
.venv/bin/python -m pytest tests/

# From workspace root (Windows PowerShell)
.\.venv\Scripts\python.exe -m pytest tests/

# Or activate the environment first, then use the portable form
python -m pytest tests/ web/backend/tests/ backend/
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
- **pytest runner**: the Python interpreter selected by the Python extension

## Why This Matters

The bot and backend have separate `conftest.py` files that conflict if pytest's discovery includes both. Running from workspace root with explicit paths (`tests/` or `web/backend/tests/`) prevents this issue.

## Environment Setup

The checked-in configuration expects an environment named `.venv`. It resolves
`.venv/bin/python` on Linux/macOS and `.venv\Scripts\python.exe` on Windows.
