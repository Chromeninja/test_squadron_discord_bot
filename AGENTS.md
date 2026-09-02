# Codex repository instructions

These instructions apply to the entire repository. If a more specific
`AGENTS.md` is added below a directory, its instructions take precedence for
that subtree.

## Start with repository evidence

- Read the files you will change, their nearest tests, and the relevant
  configuration before editing. Prefer established local patterns over generic
  framework examples.
- Treat `pyproject.toml`, `.pre-commit-config.yaml`, and `.github/workflows/` as
  the source of truth for enforced tooling. Documentation can lag behind them.
- Preserve unrelated user changes. Do not create commits, branches, issues, pull
  requests, or remote changes unless the user explicitly requests them.
- Never expose or commit secrets. Use `.env.example` and
  `config/config-example.yaml` only as templates; do not read or modify a user's
  populated `.env` or `config/config.yaml` unless the task requires it.

## Architecture and ownership

This is a Python 3.12 Discord bot with FastAPI services and a React/TypeScript
dashboard.

- `bot.py` is the Discord process entry point. `bot.pyi` is an IDE/type stub,
  not an implementation file; update it only when the public shape of `MyBot`
  changes.
- `cogs/` owns Discord commands and events. Cogs should delegate business logic
  through `self.bot.service_container` rather than construct services.
- `services/` is the legacy service and SQLite layer. Keep changes compatible
  with its dependency-injection and async database patterns.
- `backend/` is the preferred authoritative data/API layer for new work. Put new
  guild-scoped database access in the appropriate
  `backend/db/repository/<domain>.py` repository and expose it through the
  existing API/connector boundaries.
- `connectors/` is the bot's typed HTTP client boundary to `backend/`. Access
  domain connectors through `self.bot.connectors`.
- `web/backend/` is the dashboard FastAPI application. It owns OAuth/session
  behavior and talks to bot/backend APIs through existing clients.
- `web/frontend/` is the React 18 + TypeScript + Vite application.
- `verification/` owns RSI parsing and verification. Preserve circuit-breaker
  behavior and mock RSI traffic in tests.

The system is mid-migration. Do not introduce a second path to the same data or
move legacy code merely because it is nearby; follow the boundary used by the
feature being changed. Consult `CLAUDE.md` and
`documents/backend-first-migration.md` when a change crosses process or data
boundaries.

## Implementation conventions

- Keep async paths non-blocking. Use the project's async HTTP and database
  clients, and bound concurrency when operating on many Discord members or
  external requests.
- Add type annotations to new and changed functions. Use Python 3.12 syntax and
  keep code compatible with Ruff's 88-character formatter.
- Use timezone-aware UTC values (`datetime.now(timezone.utc)`), `pathlib` for new
  filesystem code, and module-level `logging` for operational output.
- Parameterize SQL values; never interpolate untrusted values into SQL. Keep
  related writes in one transaction and preserve guild scoping.
- Validate data at external boundaries (Discord input, HTTP payloads,
  configuration, and scraped content). Do not log tokens, session values, API
  keys, or sensitive user payloads.
- Preserve FastAPI dependency injection, Discord permission checks, correlation
  IDs, and API-key authentication when modifying protected routes.
- Prefer small, domain-focused modules. `tools/check_modularity.py` warns above
  500 lines, 15 functions, or 4 classes and fails non-test Python files above
  700 lines. Do not grow files over their recorded legacy ceiling.
- Avoid broad cleanup, speculative abstractions, dependency upgrades, and
  generated-file churn outside the requested change.

## Tests and verification

Add or update tests for every behavior change, including failure and permission
paths where relevant. Use existing fixtures/factories (`temp_db`, `mock_bot`,
and `tests/factories/`) and mock Discord, RSI, and other network calls.

Run the narrowest useful checks first, then expand in proportion to the change:

```text
pytest path/to/test_file.py -q
ruff check <changed Python paths>
ruff format --check <changed Python paths>
```

For backend or connector changes, also run the CI type-check command:

```text
mypy backend/ connectors/ --ignore-missing-imports --no-strict-optional --follow-imports=silent --exclude "(test_.*\.py|conftest\.py)$" --disable-error-code=no-any-return
```

For frontend changes, run from `web/frontend/`:

```text
npm run lint
npm test -- --run
npm run build
```

Before handing off a broad Python change, prefer:

```text
pre-commit run --all-files
pytest -q
```

Do not claim a check passed unless it was run. If a check cannot run because of
missing dependencies, credentials, services, or environment limitations,
report that clearly and include the narrower checks that did run.

## Change-specific checks

- Schema/repository changes: test migrations, transaction rollback, guild
  isolation, and repository/API/connector contracts.
- Discord changes: test permission denial, missing guild/member/role state, and
  Discord API failures without making live calls.
- Authentication/session changes: test unauthenticated, unauthorized, expired,
  and valid cases; never weaken production checks to simplify development.
- Dependency changes: update the appropriate lock or requirement files and run
  the relevant audit (`pip-audit` or `npm audit --audit-level=high`).
- Docker/startup changes: validate both `Dockerfile.bot` and
  `Dockerfile.backend` when the shared runtime or dependency set changes.

## Handoff

Summarize the user-visible outcome, identify changed files, and list checks run
with their results. Call out remaining risks or unverified checks directly; do
not hide failures or dismiss them as pre-existing.
