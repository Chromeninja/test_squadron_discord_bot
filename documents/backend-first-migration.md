# Backend-First Migration Roadmap

Last updated: 2026-06-01

This document tracks the in-progress migration of TEST Squadron from an in-process
service architecture to a **backend-first** design where a single FastAPI backend
(`web/backend/` + the `backend/` package) is the authoritative owner of all database
access, and the Discord bot + React frontend are HTTP clients.

It is the source of truth for the multi-session cutover. Update the status boxes as
work lands.

## Target architecture

```
Discord Bot ──(connectors/, HTTP X-Bot-Api-Key)──┐
React Frontend ──(fetch, OAuth cookie)────────────┤──→ FastAPI backend ──→ SQLite/Postgres
                                                   ┘     (sole DB owner)
```

- **DB owner:** only `backend/db/repository/` touches the database.
- **Backend services:** `backend/services/` hold orchestration that is *not* Discord-specific.
- **Bot services:** keep Discord orchestration (threads, roles, embeds, voice state) but
  source their *data* from the backend via `connectors/`.
- **Hot paths stay in-process:** voice gateway events (`cogs/voice/events.py`) and metric
  ingestion (`MetricsService.record_*`) do NOT make per-event HTTP calls — that is a
  chatty-I/O anti-pattern and breaks the 3s interaction budget. Only command-path and
  dashboard-facing operations route through the backend.

## Key architectural facts (from service surface audit)

| Service | Methods | Dominant class | Disposition |
|---------|---------|----------------|-------------|
| `TicketService` | ~38 | PURE-DB | Port DB → `backend/db/repository/tickets.py`; thin Discord bits stay in cog |
| `TicketFormService` | ~23 | PURE-DB | Port DB → `backend/db/repository/ticket_forms.py` |
| `ConfigService` | ~28 | PURE-DB (`guild_settings`) | Port DB → `ConfigRepository` (started); keep in-memory cache in bot |
| `GuildConfigHelper` | ~14 | DISCORD-ORCH | Stays in bot; resolves IDs→objects, calls config connector for data |
| `VerificationState` | 3 | 2 PURE-DB + 1 MIXED (RSI HTTP) | DB funcs → repo; RSI scrape stays in bot |
| `VerificationBulkService` | ~18 | DISCORD-ORCH | Stays in bot; calls verification connector for data |
| `VoiceService` (7 mixins) | ~55 | ~45% PURE-DB, ~30% MIXED, ~25% ORCH | Split per-method; **EVENTS path stays in-process** |
| `MetricsService` (+mixins) | ~40 | ~100% PURE-DB | Reads already via `routes/metrics.py`; ingestion stays in-process |

## Phasing

### Phase A — Additive endpoint + connector skeleton — ✅ DONE
- `backend/api/internal/{events,metrics,config,tickets,verification,voice}.py`
- `backend/db/repository/{events,tickets,verification,voice,config}.py`
- `connectors/` aligned to real backend routes; phantom `/events/sync` + hot-path
  `metrics.track()` removed.
- Bot unchanged at runtime (still uses `ServiceContainer`). 1442+33 tests green.

### Stage 1 — Port full DB surface into backend (additive, bot stays runnable)
Per domain: expand `backend/db/repository/<domain>.py` to cover every PURE-DB method the
service exposes, add the matching `backend/api/internal/<domain>.py` routes, expand the
domain connector, and add integration tests against the real schema. The bot keeps using
`ServiceContainer`, so nothing breaks during this stage.

- [x] **Config** — full `ConfigService` read/write surface (foundational; everything depends on it)
- [x] **Tickets** — categories, channel configs, ticket lifecycle, stats
- [x] **Ticket forms** — steps, questions, sessions, responses
- [x] **Verification** — covered by Phase A `VerificationRepository` (the `verification` table is the
      global state store; `store_global_state`/`get_global_state` map to `create`/`get_verification`).
      `compute_global_state` (RSI HTTP scrape) and `VerificationBulkService` are Discord-orchestration
      and stay in the bot by design — no backend port needed.
- [ ] **Voice (command-path only)** — JTC config, ownership transfer/claim, settings snapshots, admin reset/purge
- [x] **Metrics** — reads already served by `web/backend/routes/metrics.py`; ingestion stays in-process. No port needed.

### Stage 2 — Coordinated breaking cutover (bot requires backend after this)
One pass, behind a release boundary:
- [ ] Rewire command cogs to `self.bot.connectors.<domain>` (keep voice EVENTS + metrics
      ingestion in-process)
- [ ] Slim `ServiceContainer`: keep `VoiceService` (events) + `MetricsService` (ingestion);
      drop migrated DB-only services
- [ ] Invert dashboard: `web/backend/routes/*` call `backend/services/` in-process instead
      of the bot's `internal_api`; retire `services/internal_api.py` + `internal_api_client`
- [ ] Delete migrated direct-DB service code
- [ ] `frontend/src/api/endpoints.ts` base URL → unified backend
- [ ] Deployment: `docker compose up` becomes canonical (bot waits on backend healthcheck);
      document the new two-process requirement in SETUP.md

### Stage 3 — Long-term scalability (independent of cutover)
The repository seam makes these single-layer swaps:
- [ ] SQLite → PostgreSQL (Alembic migrations; PgBouncer pooling)
- [ ] Redis cache for hot guild-config reads (5–10 min TTL)
- [ ] `AutoShardedBot` + external sharding plan (shard before 2,500 guilds)
- [ ] Short-lived JWT (rotating) for bot↔backend auth in place of the static API key
- [ ] OpenTelemetry tracing across bot→backend on the existing correlation-ID propagation

## Deployment impact

Until Stage 2 lands, deployment is unchanged (the bot runs standalone). **After Stage 2,
the bot requires the backend process to be reachable** — `docker compose up` (backend +
bot, shared DB volume, bot gated on backend healthcheck) becomes the supported method.
