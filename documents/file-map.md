# Repository File Map

Last updated: 2026-05-20

This map provides a quick view of how the repository is organized, with each major folder and its files/subfolders.

## Top-level files

- `.editorconfig` — Cross-editor formatting rules.
- `.env.example` — Environment variable template.
- `.gitattributes` — Git attribute configuration.
- `.gitignore` — Ignored files and directories.
- `.pre-commit-config.yaml` — Pre-commit hook configuration.
- `.python-version` — Python version pinning for local tooling.
- `CLAUDE.md` — Agent-facing project instructions.
- `CONTRIBUTING.md` — Contributor workflow and standards.
- `LICENSE` — Project license.
- `PRIVACY.md` — Data handling/privacy policy.
- `README.md` — Primary project overview and usage.
- `SECURITY.md` — Security policy and reporting guidance.
- `SETUP.md` — Deployment and setup instructions.
- `VS_CODE_SETUP.md` — VS Code local development setup.
- `bot.py` — Main Discord bot runtime entrypoint.
- `bot.pyi` — Type stub for bot attributes/contracts.
- `bot_tasks.py` — Bot task orchestration helpers.
- `discord-bot.code-workspace` — VS Code workspace config.
- `pyproject.toml` — Python tooling/lint/type config.
- `pytest.ini` — Pytest configuration.
- `requirements-dev.txt` — Development dependencies.
- `requirements.txt` — Runtime dependencies.
- `start_bot.py` — Startup wrapper for bot run flow.

## Top-level directories

### `.github/`
GitHub automation, CI, and coding instructions.

- `codeql/`
  - `codeql-config.yml`
- `instructions/`
  - `database.instructions.md`
  - `python.instructions.md`
  - `tests.instructions.md`
- `skills/`
  - `gh-pr-edit/`
  - `github-issue-tracking/`
  - `pre-commit-checks/`
  - `security-scan/`
- `workflows/`
  - `codeql.yml`
  - `tests.yml`
- `copilot-instructions.md`
- `dependabot.yml`

### `.vscode/`
Editor configuration and debug tasks.

- `README.md`
- `extensions.json`
- `launch.json`
- `settings.json`
- `tasks.json`

### `cogs/`
Discord command/event modules grouped by domain.

- `__init__.py`
- `admin/`
  - `__init__.py`
  - `check_user.py`
  - `commands.py`
  - `member_lifecycle.py`
  - `new_member_role_worker.py`
  - `recheck.py`
  - `role_delegation.py`
  - `verify_bulk.py`
- `info/`
  - `__init__.py`
  - `about.py`
  - `dashboard.py`
  - `help.py`
  - `privacy.py`
- `metrics/`
  - `__init__.py`
  - `events.py`
- `tickets/`
  - `__init__.py`
  - `commands.py`
- `verification/`
  - `__init__.py`
  - `commands.py`
- `voice/`
  - `__init__.py`
  - `commands.py`
  - `events.py`
  - `service_bridge.py`

### `config/`
Configuration loading and examples.

- `__init__.py`
- `config-example.yaml`
- `config_loader.py`

### `documents/`
Centralized repository documentation.

- `README.md`
- `file-map.md`

### `helpers/`
Reusable utility modules used across bot domains.

- `__init__.py`
- `announcement.py`
- `announcement_bulk_cog.py`
- `audit.py`
- `bot_protocol.py`
- `bot_utils.py`
- `bulk_check.py`
- `circuit_breaker.py`
- `cog_loader.py`
- `constants.py`
- `daily_activity_tracker.py`
- `decorators.py`
- `discord_api.py`
- `discord_reply.py`
- `embeds.py`
- `embeds_factory.py`
- `embeds_voice.py`
- `error_messages.py`
- `http_helper.py`
- `leadership_log.py`
- `leadership_log_models.py`
- `modals.py`
- `permissions_helper.py`
- `rate_limiter.py`
- `recheck_service.py`
- `role_helper.py`
- `role_ids.py`
- `role_select_utils.py`
- `secure_random.py`
- `snapshots.py`
- `task_queue.py`
- `ticket_form_views.py`
- `ticket_views.py`
- `ticket_views_action.py`
- `ticket_views_helpers.py`
- `ticket_views_thread.py`
- `token_manager.py`
- `username_404.py`
- `verification_logging.py`
- `verification_messages.py`
- `views.py`
- `views_admin.py`
- `views_feature.py`
- `views_verification.py`
- `views_voice.py`
- `voice_permissions.py`
- `voice_repo.py`
- `voice_settings.py`
- `voice_utils.py`

### `prompts/`
AI-support documentation, templates, and schemas.

- `README.md`
- `messages/`
  - `verification.md`
- `schemas/`
  - `api_responses.json`
  - `database_models.json`
  - `discord_events.json`
- `system/`
  - `development_guide.md`
  - `error_analysis.md`

### `services/`
Business logic services and service container wiring.

- `__init__.py`
- `base.py`
- `config_service.py`
- `event_sync_service.py`
- `guild_config_helper.py`
- `guild_service.py`
- `guild_sync.py`
- `health_service.py`
- `internal_api.py`
- `internal_api_metrics_mixin.py`
- `log_cleanup.py`
- `metrics_activity.py`
- `metrics_buckets.py`
- `metrics_flush.py`
- `metrics_models.py`
- `metrics_queries.py`
- `metrics_read.py`
- `metrics_service.py`
- `new_member_role_service.py`
- `role_delegation_service.py`
- `service_container.py`
- `ticket_form_service.py`
- `ticket_rate_limiter.py`
- `ticket_service.py`
- `verification_bulk_service.py`
- `verification_scheduler.py`
- `verification_state.py`
- `voice_base_mixin.py`
- `voice_channel_helpers.py`
- `voice_channel_mixin.py`
- `voice_create_mixin.py`
- `voice_jtc_mixin.py`
- `voice_reconcile_mixin.py`
- `voice_service.py`
- `voice_settings_mixin.py`
- `voice_setup_mixin.py`
- `voice_state_mixin.py`
- `db/`
  - `__init__.py`
  - `database.py`
  - `managed_event_mapper.py`
  - `membership.py`
  - `metrics_db.py`
  - `repository.py`
  - `schema.py`

### `tests/`
Automated test suite for bot, services, and integration behavior.

- `conftest.py`
- `sample_rsi_organizations.html`
- `sample_rsi_profile.html`
- `voice_test_helpers.py`
- `factories/`
  - `__init__.py`
  - `config_factories.py`
  - `db_factories.py`
  - `discord_factories.py`
  - `html_factories.py`
- `permissions/`
  - `test_permissions_helper.py`
- `roles/`
  - `test_role_select_utils.py`
- `services/`
  - `test_voice_service.py`
- `test_*.py` files at this level cover admin, verification, voice, metrics, tickets, DB, and integration flows.

### `tools/`
Repository maintenance and diagnostic scripts.

- `check_modularity.py`
- `rsi_probe.py`

### `utils/`
Cross-cutting runtime utility code.

- `__init__.py`
- `about_metadata.py`
- `log_context.py`
- `logging.py`
- `tasks.py`
- `types.py`

### `verification/`
RSI verification domain logic.

- `__init__.py`
- `rsi_verification.py`

### `web/`
Web admin dashboard backend and frontend projects.

- `backend/`
  - `.vscode/settings.json`
  - `app.py`
  - `requirements.txt`
  - `core/` (auth, permission, validation, API client, session, security helpers)
  - `routes/` (FastAPI route modules)
  - `tests/` (backend API and security tests)
- `frontend/`
  - `index.html`
  - `package.json`
  - `package-lock.json`
  - `postcss.config.js`
  - `tailwind.config.js`
  - `tsconfig.json`
  - `tsconfig.node.json`
  - `vite.config.ts`
  - `vitest.config.ts`
  - `public/` (static assets)
  - `src/` (React app code, components, pages, hooks, contexts, utilities)

## Notes

- This map intentionally excludes `.git/`, cache folders (for example `.ruff_cache/`), and other generated artifacts.
- Update this file whenever repository structure changes.
