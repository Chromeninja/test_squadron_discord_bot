# VS Code Setup for TEST Squadron Discord Bot

A concise guide to get VS Code ready for developing and debugging the full stack (bot + backend + frontend).

## 1) Prereqs
- VS Code (latest)
- Python 3.12+ available on your system (repo uses `venv`)
- Node.js 20+ (for frontend + unit tests)
- Repo cloned locally

## 2) Recommended extensions (auto-suggested by `.vscode/extensions.json`)
- `ms-python.python`
- `ms-python.vscode-pylance`
- `ms-python.python-test-adapter`
- `ms-azuretools.vscode-docker` (Docker)
 - `esbenp.prettier-vscode` (optional)
 - `dbaeumer.vscode-eslint` (optional)

## 3) Open the workspace
- Open the folder `/home/chrome/test_squadron_discord_bot` in VS Code.
- VS Code should pick up `.vscode/settings.json`, `.vscode/launch.json`, and `.vscode/tasks.json` automatically.

## 4) Select the interpreter
- Command Palette: `Python: Select Interpreter` → choose `${workspaceFolder}/.venv/bin/python`.
- This ensures the Testing view, debugger, and terminals use the project venv.

## 5) Environment file
- Create `.env` in the repo root (shared by bot and backend). See `SETUP.md` for example values.

## 6) Install dependencies
```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install -r web/backend/requirements.txt
pip install -r requirements-dev.txt
cd web/frontend && npm install && cd ../..
```

Frontend test environment:
- Vitest is installed via `npm install`
- DOM environment: `happy-dom` is configured in `vite.config.ts` (install with `npm install -D happy-dom` if prompted)

## 7) Launch / Debug
Use the built-in launch configs (Run and Debug panel):
- **🚀 Full Stack (Bot + Web Admin)** — launches bot, backend (uvicorn), frontend (Vite) together
- **Start Bot (start_bot.py)** — bot only
- **Web Backend (FastAPI)** — backend only
- **Web Frontend (Vite Dev Server)** — frontend only

Breakpoints: set in Python or frontend code, then run the corresponding config.

## 8) Running the Full Stack via Docker
For **integration testing and full-stack validation** that mirrors production, use Docker Compose. Docker is ideal when you need the bot and backend in isolated containers with real networking — use native launch configs (above) when you need breakpoint debugging in individual processes.

### Prerequisites
- Ensure `.env` is populated in the repo root (see `SETUP.md` for required fields).
- `config/config.yaml` must exist with correct channel/role IDs for your test server.

### Available Docker tasks
Command Palette → `Tasks: Run Task`, then select:
- **`docker: compose up (build)`** — Builds and starts bot + backend + SQLite volume; logs to terminal. Hit Ctrl+C to stop.
- **`docker: compose up (detached)`** — Same, but runs in background (headless). Use with Docker extension panel or `docker: compose logs` task to monitor.
- **`docker: compose build`** — Rebuild images without starting containers.
- **`docker: compose logs`** — Stream logs from running containers (follow mode).
- **`docker: compose down`** — Stop and remove containers (volumes persist; see "Volume persistence" below).

### Running the stack step-by-step
1. Open Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`).
2. Type `Tasks: Run Task` and press Enter.
3. Select **`docker: compose up (build)`** to start the full stack with output in the terminal.
   - The backend (FastAPI) starts on `http://localhost:8000`
   - The bot waits for the backend to be healthy before connecting.
4. Once you see log output, verify health: open a terminal and run:
   ```bash
   curl http://localhost:8000/api/v1/health
   ```
   Expected response: `{"status":"ok"}` (or similar).

### Managing containers and logs
The **Docker extension** (`ms-azuretools.vscode-docker`) provides a visual interface:
- Open the Docker panel (whale icon in the Activity Bar).
- **Containers** tab: see `bot` and `backend` containers, their status, and running processes.
  - Right-click a container → "View Logs" to see its output.
  - Right-click → "Attach Shell" to execute commands inside a container.
- **Images** tab: inspect built images (`backend:latest`, `bot:latest`).

Alternatively, use the **`docker: compose logs`** task to stream logs in the terminal.

### Volume persistence
The `sqlite-data` volume persists the SQLite databases (`guild_data.db`, etc.) between container restarts. When you run `docker: compose down`, the volume is **not** deleted — data survives.
- To wipe data, run `docker volume rm test_squadron_discord_bot_sqlite-data` (replace with your volume name).
- To view stored data, attach a shell to the `backend` container and browse `/app/data/`.

### Tearing down
Run the **`docker: compose down`** task to stop all containers and clean up networks. Volumes and images remain for faster restarts.

## 9) Testing in VS Code
- Open the Testing view (beaker icon). Tests are auto-discovered from `tests/` and `web/backend/tests/`.
- Run/Debug all tests or individual tests from the tree.
- CLI equivalent (backend/bot):
	```bash
	.venv/bin/python -m pytest tests/ web/backend/tests/ -v
	```
- Frontend tests (Vitest):
	```bash
	cd web/frontend
	npm test -- --run
	```

## 10) Tasks (optional shortcuts)
Command Palette → `Tasks: Run Task`:
- `pytest: bot tests`
- `pytest: backend tests`
- `pytest: all tests`
- Quick modes are also available.

Optional frontend tasks (if added to `tasks.json`):
- `vitest: unit tests`
- `vite: dev server`

## 11) Common tips
- If debugpy complains about missing modules, ensure `.venv` is active and deps are installed.
- If Testing view shows discovery errors, reload the window (`Developer: Reload Window`) after installing deps.
- Keep the `.env` file up to date; it is read by launch configs for bot/backend.
