# VS Code Setup for TEST Squadron Discord Bot

A concise guide to get VS Code ready for developing and debugging the full stack (bot + backend + frontend).

## 1) Prereqs
- VS Code (latest)
- Python 3.8+ available on your system
- Node.js 18+ (for frontend)
- Repo cloned locally

## 2) Recommended extensions (auto-suggested by `.vscode/extensions.json`)
- `ms-python.python`
- `ms-python.vscode-pylance`
- `ms-python.python-test-adapter`

## 3) Open the workspace
- Open the folder `/home/chrome/test_squadron_discord_bot` in VS Code.
- VS Code should pick up `.vscode/settings.json`, `.vscode/launch.json`, and `.vscode/tasks.json` automatically.

## 4) Select the interpreter
- Command Palette: `Python: Select Interpreter` → choose `${workspaceFolder}/.venv/bin/python`.
- This ensures the Testing view, debugger, and terminals use the project venv.

## 5) Environment file
- Create `.env` in the repo root (shared by bot and backend). See `SETUP.txt` for example values.

## 6) Install dependencies
```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install -r web/backend/requirements.txt
pip install -r requirements-dev.txt
cd web/frontend && npm install && cd ../..
```

## 7) Launch / Debug
Use the built-in launch configs (Run and Debug panel):
- **🚀 Full Stack (Bot + Web Admin)** — launches bot, backend (uvicorn), frontend (Vite) together
- **Start Bot (start_bot.py)** — bot only
- **Web Backend (FastAPI)** — backend only
- **Web Frontend (Vite Dev Server)** — frontend only

Breakpoints: set in Python or frontend code, then run the corresponding config.

## 8) Testing in VS Code
- Open the Testing view (beaker icon). Tests are auto-discovered from `tests/` and `web/backend/tests/`.
- Run/Debug all tests or individual tests from the tree.
- CLI equivalent: `.venv/bin/python -m pytest tests/ web/backend/tests/ -v`.

## 9) Tasks (optional shortcuts)
Command Palette → `Tasks: Run Task`:
- `pytest: bot tests`
- `pytest: backend tests`
- `pytest: all tests`
- Quick modes are also available.

## 10) Common tips
- If debugpy complains about missing modules, ensure `.venv` is active and deps are installed.
- If Testing view shows discovery errors, reload the window (`Developer: Reload Window`) after installing deps.
- Keep the `.env` file up to date; it is read by launch configs for bot/backend.
