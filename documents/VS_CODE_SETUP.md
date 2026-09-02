# VS Code Setup — TEST Squadron Discord Bot

This guide gets VS Code ready for the full stack. **Docker Compose is the primary way to run the bot and backend.** The Python venv is only used for running tests and linters locally.

## 1. Prerequisites

- VS Code (latest)
- Docker Engine and `docker compose` plugin ([install guide](https://docs.docker.com/engine/install/))
- Python 3.12+ (for running pytest and linting locally)
- Node.js 20+ (for frontend tests and Vite dev server)

## 2. Running the Stack (Docker — primary workflow)

Docker Compose is how you run the bot and backend during local development. It mirrors the production environment exactly.

### Setup

1. **Open the repo folder** in VS Code.
2. **Create `.env`** from the example and fill in your Discord credentials and secrets:
   ```bash
   cp .env.example .env
   # Required: DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, SESSION_SECRET, BOT_API_KEY
   ```
3. **Create `config/config.yaml`** from the example:
   ```bash
   cp config/config-example.yaml config/config.yaml
   ```

### Start via VS Code Tasks

Command Palette (`Ctrl+Shift+P`) → **Tasks: Run Task**:

| Task | Effect |
|------|--------|
| `docker: compose up (build)` | Build images and start bot + backend; logs stream to terminal |
| `docker: compose up (detached)` | Same, runs in background |
| `docker: compose build` | Rebuild images without starting |
| `docker: compose logs` | Stream logs from running containers |
| `docker: compose down` | Stop containers (data volume persists) |

### Start via terminal

```bash
docker compose up --build          # foreground — Ctrl+C to stop
docker compose up -d --build       # detached
docker compose logs -f             # stream all logs
docker compose logs -f backend     # backend only
docker compose logs -f bot         # bot only
docker compose down                # stop (data persists)
docker compose down -v             # stop + wipe data
```

### Verify

Once running, the backend health endpoint should respond:
```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status":"ok"} or similar
```

### Docker extension

The **Docker** extension (`ms-azuretools.vscode-docker`) gives you a visual view of containers:
- **Containers** tab: see `bot` and `backend` status, right-click → "View Logs" or "Attach Shell"
- **Images** tab: inspect built images

### Data persistence

SQLite databases live in the `./data/` bind mount (`/app/data/` inside containers). They persist across `docker compose down` and rebuilds. To wipe all data: `docker compose down -v`.

## 3. Python Interpreter (for tests and linting only)

The venv is **not** used to run the bot or backend — Docker handles that. Set it up to get test discovery, type checking, and linting in VS Code.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r web/backend/requirements.txt -r requirements-dev.txt
pre-commit install
```

Command Palette → **Python: Select Interpreter** → choose `.venv/bin/python` (or `.venv\Scripts\python.exe` on Windows).

## 4. Recommended Extensions

Auto-suggested via `.vscode/extensions.json`:

- `ms-python.python` + `ms-python.vscode-pylance` — Python language support
- `ms-python.python-test-adapter` — Test discovery in the Testing view
- `ms-azuretools.vscode-docker` — Docker container management
- `esbenp.prettier-vscode` — Frontend formatting (optional)
- `dbaeumer.vscode-eslint` — Frontend linting (optional)

## 5. Debugging Individual Processes

If you need **breakpoint debugging** in a single process (not the full Docker stack), use the pre-configured launch configs (Run and Debug panel, `Ctrl+Shift+D`):

| Config | What it runs |
|--------|--------------|
| 🚀 Full Stack (Bot + Web Admin) | Bot + backend + frontend natively (debugpy/Vite) |
| Start Bot (start_bot.py) | Bot only |
| Web Backend (FastAPI) | Backend only (uvicorn) |
| Web Frontend (Vite Dev Server) | Frontend only |

> Use Docker for integration testing and full-stack validation. Use native launch configs when you need Python breakpoints inside a specific process.

## 6. Testing in VS Code

Tests run against the local venv — they do **not** require Docker to be running.

### Testing view

Open the Testing view (beaker icon). Tests are auto-discovered from `tests/` and `web/backend/tests/`.

### CLI

```bash
# From repo root (venv active)
pytest tests/ web/backend/tests/ -v          # All tests
pytest tests/ -v                             # Bot/cog/service tests
pytest web/backend/tests/ -v                 # Web dashboard tests
pytest --cov --cov-fail-under=50             # With coverage
```

### Frontend tests (Vitest)

```bash
cd web/frontend
npm test -- --run
```

### VS Code tasks

Command Palette → Tasks: Run Task:
- `pytest: bot tests`
- `pytest: backend tests`
- `pytest: all tests`

## 7. Common Tips

- If debugpy complains about missing modules, ensure the venv is active and the canonical dependency install command above has been run.
- If the Testing view shows discovery errors, reload the window (`Developer: Reload Window`) after installing deps.
- Keep `.env` up to date — it is read by both Docker Compose and the native launch configs.
- The Docker stack and the native launch configs share the same `.env` file — you do not need separate configs for each.
