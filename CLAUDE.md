# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Dev Environment Setup

```bash
# 1. Copy and populate environment file
cp .env.example .env
# Fill in DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, SESSION_SECRET, BOT_API_KEY

# 2. Copy and customize config
cp config/config-example.yaml config/config.yaml

# 3. Start services (Docker)
docker compose up --build          # Build and start bot + backend (foreground)
docker compose up -d --build       # Same, detached (background)
docker compose logs -f             # Stream logs
docker compose down                # Stop all services

# 4. Tests & linting (venv — never used to run services)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

## Commands

```bash
# Run (Docker Compose — primary)
docker compose up --build          # Start bot + backend, stream logs
docker compose up -d --build       # Start detached (background)
docker compose logs -f             # Stream all logs
docker compose logs -f backend     # Backend logs only
docker compose logs -f bot         # Bot logs only
docker compose down                # Stop all services
docker compose down -v             # Stop and wipe data volumes

# Bot (direct — only for debugging outside Docker)
python3 bot.py                         # Run the Discord bot
python3 start_bot.py                   # Run via startup wrapper

# Tests (run from repo root)
pytest tests/ -v                       # Bot/cog/service tests
pytest web/backend/tests/ -v           # Web dashboard tests
pytest backend/ -v                     # Repository integration tests (DB-backed)
pytest tests/test_rsi_verification.py  # Single test file
pytest -m unit                         # Unit tests only
pytest -m integration                  # Integration tests (skipped by default)
pytest --cov --cov-fail-under=50       # With coverage (50% minimum; target 70%)

# Linting / type checking
ruff check .                           # Lint
ruff format .                          # Format
mypy --strict bot.py cogs/ services/ helpers/ verification/ utils/  # Type check (legacy)
mypy backend/ connectors/ --ignore-missing-imports --no-strict-optional \
  --follow-imports=silent --disable-error-code=untyped-decorator \
  --disable-error-code=no-any-return   # Type check (new backend-first layer)

# Modularity check (run before committing)
python3 tools/check_modularity.py $(git diff --name-only --diff-filter=AM HEAD -- '*.py')

# Pre-commit (runs all quality gates)
pre-commit run --all-files
```

## Architecture

### Three-process system

The project runs as three separate processes that communicate:

1. **Discord bot** (`bot.py`) — `MyBot` (discord.py subclass) handles all Discord events and slash commands
2. **Internal API** (`services/internal_api.py`) — FastAPI server embedded in the bot process on port 8082; bot services are exposed over HTTP to the web backend
3. **Web dashboard** (`web/backend/app.py`) — Separate FastAPI server on port 8000 handling Discord OAuth2 and the management UI; calls the internal API via `web/backend/core/internal_api_client.py`

The web frontend (`web/frontend/`) is a React + TypeScript SPA that calls the web backend.

### Auth keys

Two separate API keys protect the inter-process boundary:
- `INTERNAL_API_KEY` — used by the web backend to call the bot's internal API (`services/internal_api.py`)
- `BOT_API_KEY` — docker-compose alias for `INTERNAL_API_KEY`; used by the bot to call the new `backend/` FastAPI server

In `ENV=development` or `dev`, `INTERNAL_API_KEY` is not required. In production it must be set.

### Backend-first layer (in progress)

A new `backend/` package is being built as the authoritative data layer. New code should use it; existing code is being migrated incrementally:

- **`backend/db/repository/`** — guild-scoped DB query methods (one file per domain). All new DB access should go through these classes rather than calling `Database` directly.
- **`backend/api/internal/`** — FastAPI routes protected by `X-Bot-Api-Key` header (`BOT_API_KEY` env var). These will replace the embedded `InternalAPIServer` for DB-backed operations.
- **`backend/api/v1/`** — Public versioned endpoints (`/api/v1/health`, `/api/v1/metrics`).
- **`backend/middleware/`** — Structured JSON logging with correlation IDs; global error handler.
- **`backend/auth/api_key.py`** — FastAPI `Depends` for bot-to-backend API key auth.
- **`connectors/`** — HTTP client layer for the bot to call the backend (`BotAPIConnector` + domain connectors). Access via `self.bot.connectors.<domain>` — available when `BACKEND_URL` and `BOT_API_KEY` are set.
- **`connectors/registry.py`** — `ConnectorRegistry` dataclass; the typed handle for all domain connectors.

### Bot startup flow

`bot.py::setup_hook()` runs in order:
1. DB schema init (`services/db/database.py`)
2. `ServiceContainer` constructed with all services injected
3. Internal API server started (background task)
4. Task queue workers started
5. All cogs loaded via `helpers/cog_loader.py`
6. Persistent Discord views registered (survives bot restarts)
7. App commands synced to Discord

`bot.pyi` is a stub file for IDE type hints only — do not edit it for logic changes.

### Cog structure

Each feature domain under `cogs/` follows a consistent pattern:

```
cogs/<domain>/
├── __init__.py
├── commands.py   # Slash command definitions
└── events.py     # Discord event listeners
```

Some domains add extra files (e.g., `cogs/verification/` has `recheck.py`, `verify_bulk.py`, `check_user.py`; `cogs/voice/` has `service_bridge.py`). Commands call into `self.bot.service_container.<service>` — never instantiate services directly in cogs.

### Service layer (services/)

All service singletons are registered in `services/service_container.py` and injected throughout — do not instantiate services directly in cogs. Access via `self.bot.service_container.<service>`.

**VoiceService** uses mixin composition — the class at `services/voice_service.py` inherits from 7 mixin files (`voice_*_mixin.py`). This is intentional to stay under the 700-line file limit enforced by pre-commit.

**Database pattern**: `services/db/database.py` manages a single `aiosqlite` connection. All table access goes through `services/db/repository.py` (`BaseRepository`). Schema is defined in `services/db/schema.py` and migrations are tracked in `schema_migrations`.

**Task queue**: `helpers/task_queue.py` handles background work with retry logic. Workers are started in `setup_hook()`.

### RSI verification flow

`verification/rsi_verification.py` scrapes RSI profiles via BeautifulSoup. The circuit breaker (`helpers/circuit_breaker.py`) prevents hammering RSI's site. Returns `verify_value`: 1=main org member, 2=affiliate, 0=non-member.

### Permission hierarchy

`helpers/permissions_helper.py` defines 6 levels: Bot Owner > Bot Admin > Discord Manager > Moderator > Staff > Regular. Role IDs are stored per-guild in the DB (not using Discord's built-in admin permission). Command guards use `helpers/decorators.py`.

### Configuration

- `config/config.yaml` — runtime settings (channel IDs, role IDs, rate limits, org metadata)
- `.env` / environment variables — secrets and deployment settings (see `.env.example`)
- `config/config_loader.py` — validates and provides typed access via `ConfigLoader`
- `PUBLIC_URL` is the single source of truth for all external URLs; OAuth redirect URIs are derived from it automatically.

### Modularity limit

A pre-commit hook (`tools/check_modularity.py`) warns at 500 lines and **fails at 700 lines** for non-test Python files. Also warns at >15 functions or >4 classes. If adding significant logic to an existing file, split into a new helper/mixin before the hook blocks the commit. Legacy oversized files have recorded ceilings — they must not grow.

### Test setup

Tests use factories in `tests/factories/` for bot, guild, and member mocks. `pytest-asyncio` with `asyncio_mode = strict` and function-scoped event loops. The `conftest.py` files provide shared fixtures. Use the `temp_db` fixture for database tests and `mock_bot` for bot instance tests. Sample HTML files for RSI parsing tests live alongside test files.

Integration tests (`-m integration`) are excluded from the default `pytest` run — they require a running DB and are run explicitly.

### Web dashboard auth

`web/backend/core/auth.py` handles Discord OAuth2. Sessions are persisted via `web/backend/core/session_store.py`. The web backend authenticates users and then delegates actual data fetches to the bot's internal API.

## Coding conventions (enforced by pre-commit)

- `datetime.now(timezone.utc)` — never `utcnow()` (Ruff DTZ003 is active)
- No `print()` in production code — use `logging` (Ruff T20)
- Type hints on all functions — `mypy --strict` must pass for legacy packages
- Parameterized SQL with `?` placeholders — no f-string SQL
- Imports sorted by Ruff I rules
