# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Bot
python3 bot.py                         # Run the Discord bot
python3 start_bot.py                   # Run via startup wrapper

# Web dashboard (from web/backend/)
uvicorn app:app --reload               # Run FastAPI backend
# Frontend (from web/frontend/)
npm install && npm run dev             # Run Vite dev server

# Tests
pytest                                 # All tests
pytest -m unit                         # Unit tests only
pytest -m integration                  # Integration tests only
pytest -m "not slow"                   # Skip slow tests
pytest tests/test_rsi_verification.py  # Single test file
pytest --cov --cov-fail-under=50       # With coverage (50% minimum)

# Linting / type checking
ruff check .                           # Lint
ruff format .                          # Format
mypy --strict bot.py cogs/ services/ helpers/ verification/ utils/  # Type check
bandit -r . --exclude tests/,web/frontend/  # Security scan

# Pre-commit (runs all quality gates)
pre-commit run --all-files
```

## Architecture

### Three-process system

The project runs as three separate processes that communicate:

1. **Discord bot** (`bot.py`) — `MyBot` (discord.py subclass) handles all Discord events and slash commands
2. **Internal API** (`services/internal_api.py`) — FastAPI server embedded in the bot process; bot services are exposed over HTTP to the web backend
3. **Web dashboard** (`web/backend/app.py`) — Separate FastAPI server handling OAuth and the management UI; calls the internal API via `web/backend/core/internal_api_client.py`

The web frontend (`web/frontend/`) is a React + TypeScript SPA that calls the web backend.

### Bot startup flow

`bot.py::setup_hook()` runs in order:
1. DB schema init (`services/db/database.py`)
2. `ServiceContainer` constructed with all services injected
3. Internal API server started (background task)
4. Task queue workers started
5. All cogs loaded via `helpers/cog_loader.py`
6. Persistent Discord views registered (survives bot restarts)
7. App commands synced to Discord

### Service layer (services/)

All service singletons are registered in `services/service_container.py` and injected throughout — do not instantiate services directly in cogs. Access via `self.bot.service_container.<service>`.

**VoiceService** uses mixin composition — the class at `services/voice_service.py` inherits from 7 mixin files (`voice_*_mixin.py`). This is intentional to stay under the 700-line file limit enforced by pre-commit.

**Database pattern**: `services/db/database.py` manages a single `aiosqlite` connection. All table access goes through `services/db/repository.py` (`BaseRepository`). Schema is defined in `services/db/schema.py` and migrations are tracked in `schema_migrations`.

### RSI verification flow

`verification/rsi_verification.py` scrapes RSI profiles via BeautifulSoup. The circuit breaker (`helpers/circuit_breaker.py`) prevents hammering RSI's site. Returns `verify_value`: 1=main org member, 2=affiliate, 0=non-member.

### Permission hierarchy

`helpers/permissions_helper.py` defines 6 levels: Bot Owner > Bot Admin > Discord Manager > Moderator > Staff > Regular. Role IDs are stored per-guild in the DB (not using Discord's built-in admin permission). Command guards use `helpers/decorators.py`.

### Configuration

- `config/config.yaml` — runtime settings (channel IDs, role IDs, rate limits, org metadata)
- `.env` / environment variables — secrets and deployment settings (see `.env.example`)
- `config/config_loader.py` — validates and provides typed access via `ConfigLoader`

### Modularity limit

A pre-commit hook (`tools/check_modularity.py`) warns at 500 lines and **fails at 700 lines**. If adding significant logic to an existing file, split into a new helper/mixin before the hook blocks the commit.

### Test setup

Tests use factories in `tests/factories/` for bot, guild, and member mocks. `pytest-asyncio` with `asyncio_mode = strict` and function-scoped event loops. The `conftest.py` files provide shared fixtures. Sample HTML files for RSI parsing tests live alongside test files.

### Web dashboard auth

`web/backend/core/auth.py` handles Discord OAuth2. Sessions are persisted via `web/backend/core/session_store.py`. The web backend authenticates users and then delegates actual data fetches to the bot's internal API, which has its own key (`INTERNAL_API_KEY` env var).
