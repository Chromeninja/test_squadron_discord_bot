# Repository File Map

Last updated: 2026-05-20

This map provides a quick view of how the repository is organized, with each major folder and its files/subfolders.

## Maintenance expectations

- Treat this file as a living document and update it in the same PR whenever files are added, moved, renamed, or removed.
- Keep the generated tree section refreshed so every mapped file includes a brief purpose note.
- If a file purpose changes meaningfully, update its one-line description during that change.

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
## Full recursive tree with file purposes (generated)

```text
test_squadron_discord_bot/
├── .github/ — GitHub automation, instructions, and CI workflows.
│   ├── codeql/ — Subdirectory containing related project files.
│   │   └── codeql-config.yml — YAML configuration for tooling or workflows.
│   ├── instructions/ — Subdirectory containing related project files.
│   │   ├── database.instructions.md — Markdown documentation for this area.
│   │   ├── python.instructions.md — Markdown documentation for this area.
│   │   └── tests.instructions.md — Markdown documentation for this area.
│   ├── skills/ — Subdirectory containing related project files.
│   │   ├── gh-pr-edit/ — Subdirectory containing related project files.
│   │   │   └── SKILL.md — Markdown documentation for this area.
│   │   ├── github-issue-tracking/ — Subdirectory containing related project files.
│   │   │   └── SKILL.md — Markdown documentation for this area.
│   │   ├── pre-commit-checks/ — Subdirectory containing related project files.
│   │   │   └── SKILL.md — Markdown documentation for this area.
│   │   └── security-scan/ — Subdirectory containing related project files.
│   │       └── SKILL.md — Markdown documentation for this area.
│   ├── workflows/ — Subdirectory containing related project files.
│   │   ├── codeql.yml — YAML configuration for tooling or workflows.
│   │   └── tests.yml — YAML configuration for tooling or workflows.
│   ├── copilot-instructions.md — Markdown documentation for this area.
│   └── dependabot.yml — YAML configuration for tooling or workflows.
├── .vscode/ — VS Code settings and launch tasks.
│   ├── extensions.json — JSON configuration or schema data.
│   ├── launch.json — JSON configuration or schema data.
│   ├── README.md — Primary project overview and navigation.
│   ├── settings.json — JSON configuration or schema data.
│   └── tasks.json — JSON configuration or schema data.
├── cogs/ — Discord command and event modules grouped by domain.
│   ├── admin/ — Submodule directory for admin.
│   │   ├── __init__.py — Python package initializer.
│   │   ├── check_user.py — Python module implementing check user logic.
│   │   ├── commands.py — Python module implementing commands logic.
│   │   ├── member_lifecycle.py — Python module implementing member lifecycle logic.
│   │   ├── new_member_role_worker.py — Python module implementing new member role worker logic.
│   │   ├── recheck.py — Python module implementing recheck logic.
│   │   ├── role_delegation.py — Python module implementing role delegation logic.
│   │   └── verify_bulk.py — Python module implementing verify bulk logic.
│   ├── info/ — Submodule directory for info.
│   │   ├── __init__.py — Python package initializer.
│   │   ├── about.py — Python module implementing about logic.
│   │   ├── dashboard.py — Python module implementing dashboard logic.
│   │   ├── help.py — Python module implementing help logic.
│   │   └── privacy.py — Python module implementing privacy logic.
│   ├── metrics/ — Submodule directory for metrics.
│   │   ├── __init__.py — Python package initializer.
│   │   └── events.py — Python module implementing events logic.
│   ├── tickets/ — Submodule directory for tickets.
│   │   ├── __init__.py — Python package initializer.
│   │   └── commands.py — Python module implementing commands logic.
│   ├── verification/ — Submodule directory for verification.
│   │   ├── __init__.py — Python package initializer.
│   │   └── commands.py — Python module implementing commands logic.
│   ├── voice/ — Submodule directory for voice.
│   │   ├── __init__.py — Python package initializer.
│   │   ├── commands.py — Python module implementing commands logic.
│   │   ├── events.py — Python module implementing events logic.
│   │   └── service_bridge.py — Python module implementing service bridge logic.
│   └── __init__.py — Python package initializer.
├── config/ — Runtime configuration loading and examples.
│   ├── __init__.py — Python package initializer.
│   ├── config-example.yaml — YAML configuration for tooling or workflows.
│   └── config_loader.py — Python module implementing config loader logic.
├── documents/ — Repository documentation hub.
│   ├── file-map.md — Markdown documentation for this area.
│   └── README.md — Primary project overview and navigation.
├── helpers/ — Shared helper utilities used across features.
│   ├── __init__.py — Python package initializer.
│   ├── announcement.py — Python module implementing announcement logic.
│   ├── announcement_bulk_cog.py — Python module implementing announcement bulk cog logic.
│   ├── audit.py — Python module implementing audit logic.
│   ├── bot_protocol.py — Python module implementing bot protocol logic.
│   ├── bot_utils.py — Python module implementing bot utils logic.
│   ├── bulk_check.py — Python module implementing bulk check logic.
│   ├── circuit_breaker.py — Python module implementing circuit breaker logic.
│   ├── cog_loader.py — Python module implementing cog loader logic.
│   ├── constants.py — Python module implementing constants logic.
│   ├── daily_activity_tracker.py — Python module implementing daily activity tracker logic.
│   ├── decorators.py — Python module implementing decorators logic.
│   ├── discord_api.py — Python module implementing discord api logic.
│   ├── discord_reply.py — Python module implementing discord reply logic.
│   ├── embeds.py — Python module implementing embeds logic.
│   ├── embeds_factory.py — Python module implementing embeds factory logic.
│   ├── embeds_voice.py — Python module implementing embeds voice logic.
│   ├── error_messages.py — Python module implementing error messages logic.
│   ├── http_helper.py — Python module implementing http helper logic.
│   ├── leadership_log.py — Python module implementing leadership log logic.
│   ├── leadership_log_models.py — Python module implementing leadership log models logic.
│   ├── modals.py — Python module implementing modals logic.
│   ├── permissions_helper.py — Python module implementing permissions helper logic.
│   ├── rate_limiter.py — Python module implementing rate limiter logic.
│   ├── recheck_service.py — Python module implementing recheck service logic.
│   ├── role_helper.py — Python module implementing role helper logic.
│   ├── role_ids.py — Python module implementing role ids logic.
│   ├── role_select_utils.py — Python module implementing role select utils logic.
│   ├── secure_random.py — Python module implementing secure random logic.
│   ├── snapshots.py — Python module implementing snapshots logic.
│   ├── task_queue.py — Python module implementing task queue logic.
│   ├── ticket_form_views.py — Python module implementing ticket form views logic.
│   ├── ticket_views.py — Python module implementing ticket views logic.
│   ├── ticket_views_action.py — Python module implementing ticket views action logic.
│   ├── ticket_views_helpers.py — Python module implementing ticket views helpers logic.
│   ├── ticket_views_thread.py — Python module implementing ticket views thread logic.
│   ├── token_manager.py — Python module implementing token manager logic.
│   ├── username_404.py — Python module implementing username 404 logic.
│   ├── verification_logging.py — Python module implementing verification logging logic.
│   ├── verification_messages.py — Python module implementing verification messages logic.
│   ├── views.py — Python module implementing views logic.
│   ├── views_admin.py — Python module implementing views admin logic.
│   ├── views_feature.py — Python module implementing views feature logic.
│   ├── views_verification.py — Python module implementing views verification logic.
│   ├── views_voice.py — Python module implementing views voice logic.
│   ├── voice_permissions.py — Python module implementing voice permissions logic.
│   ├── voice_repo.py — Python module implementing voice repo logic.
│   ├── voice_settings.py — Python module implementing voice settings logic.
│   └── voice_utils.py — Python module implementing voice utils logic.
├── prompts/ — Prompt templates and schemas for AI-assisted workflows.
│   ├── messages/ — Subdirectory containing related project files.
│   │   └── verification.md — Markdown documentation for this area.
│   ├── schemas/ — Subdirectory containing related project files.
│   │   ├── api_responses.json — JSON configuration or schema data.
│   │   ├── database_models.json — JSON configuration or schema data.
│   │   └── discord_events.json — JSON configuration or schema data.
│   ├── system/ — Subdirectory containing related project files.
│   │   ├── development_guide.md — Markdown documentation for this area.
│   │   └── error_analysis.md — Markdown documentation for this area.
│   └── README.md — Primary project overview and navigation.
├── services/ — Business logic services and orchestration layers.
│   ├── db/ — Database access, schema, and repository modules.
│   │   ├── __init__.py — Python package initializer.
│   │   ├── database.py — Python module implementing database logic.
│   │   ├── managed_event_mapper.py — Python module implementing managed event mapper logic.
│   │   ├── membership.py — Python module implementing membership logic.
│   │   ├── metrics_db.py — Python module implementing metrics db logic.
│   │   ├── repository.py — Python module implementing repository logic.
│   │   └── schema.py — Python module implementing schema logic.
│   ├── __init__.py — Python package initializer.
│   ├── base.py — Python module implementing base logic.
│   ├── config_service.py — Python module implementing config service logic.
│   ├── event_sync_service.py — Python module implementing event sync service logic.
│   ├── guild_config_helper.py — Python module implementing guild config helper logic.
│   ├── guild_service.py — Python module implementing guild service logic.
│   ├── guild_sync.py — Python module implementing guild sync logic.
│   ├── health_service.py — Python module implementing health service logic.
│   ├── internal_api.py — Python module implementing internal api logic.
│   ├── internal_api_metrics_mixin.py — Python module implementing internal api metrics mixin logic.
│   ├── log_cleanup.py — Python module implementing log cleanup logic.
│   ├── metrics_activity.py — Python module implementing metrics activity logic.
│   ├── metrics_buckets.py — Python module implementing metrics buckets logic.
│   ├── metrics_flush.py — Python module implementing metrics flush logic.
│   ├── metrics_models.py — Python module implementing metrics models logic.
│   ├── metrics_queries.py — Python module implementing metrics queries logic.
│   ├── metrics_read.py — Python module implementing metrics read logic.
│   ├── metrics_service.py — Python module implementing metrics service logic.
│   ├── new_member_role_service.py — Python module implementing new member role service logic.
│   ├── role_delegation_service.py — Python module implementing role delegation service logic.
│   ├── service_container.py — Python module implementing service container logic.
│   ├── ticket_form_service.py — Python module implementing ticket form service logic.
│   ├── ticket_rate_limiter.py — Python module implementing ticket rate limiter logic.
│   ├── ticket_service.py — Python module implementing ticket service logic.
│   ├── verification_bulk_service.py — Python module implementing verification bulk service logic.
│   ├── verification_scheduler.py — Python module implementing verification scheduler logic.
│   ├── verification_state.py — Python module implementing verification state logic.
│   ├── voice_base_mixin.py — Python module implementing voice base mixin logic.
│   ├── voice_channel_helpers.py — Python module implementing voice channel helpers logic.
│   ├── voice_channel_mixin.py — Python module implementing voice channel mixin logic.
│   ├── voice_create_mixin.py — Python module implementing voice create mixin logic.
│   ├── voice_jtc_mixin.py — Python module implementing voice jtc mixin logic.
│   ├── voice_reconcile_mixin.py — Python module implementing voice reconcile mixin logic.
│   ├── voice_service.py — Python module implementing voice service logic.
│   ├── voice_settings_mixin.py — Python module implementing voice settings mixin logic.
│   ├── voice_setup_mixin.py — Python module implementing voice setup mixin logic.
│   └── voice_state_mixin.py — Python module implementing voice state mixin logic.
├── tests/ — Automated test suite and fixtures.
│   ├── factories/ — Reusable test data factories.
│   │   ├── __init__.py — Python package initializer.
│   │   ├── config_factories.py — Pytest module covering config factories behavior.
│   │   ├── db_factories.py — Pytest module covering db factories behavior.
│   │   ├── discord_factories.py — Pytest module covering discord factories behavior.
│   │   └── html_factories.py — Pytest module covering html factories behavior.
│   ├── permissions/ — Permission-specific tests.
│   │   └── test_permissions_helper.py — Pytest module covering permissions helper behavior.
│   ├── roles/ — Role and selector behavior tests.
│   │   └── test_role_select_utils.py — Pytest module covering role select utils behavior.
│   ├── services/ — Service-layer tests.
│   │   └── test_voice_service.py — Pytest module covering voice service behavior.
│   ├── conftest.py — Pytest module covering conftest behavior.
│   ├── sample_rsi_organizations.html — Pytest module covering sample rsi organizations behavior.
│   ├── sample_rsi_profile.html — Pytest module covering sample rsi profile behavior.
│   ├── test_admin_list_functionality.py — Pytest module covering admin list functionality behavior.
│   ├── test_admin_recheck_updates.py — Pytest module covering admin recheck updates behavior.
│   ├── test_admin_status.py — Pytest module covering admin status behavior.
│   ├── test_announcement_helpers.py — Pytest module covering announcement helpers behavior.
│   ├── test_announcement_logic.py — Pytest module covering announcement logic behavior.
│   ├── test_bot_startup.py — Pytest module covering bot startup behavior.
│   ├── test_bulk_check.py — Pytest module covering bulk check behavior.
│   ├── test_check_user_activity.py — Pytest module covering check user activity behavior.
│   ├── test_circuit_breaker.py — Pytest module covering circuit breaker behavior.
│   ├── test_command_handlers.py — Pytest module covering command handlers behavior.
│   ├── test_config_loader_validation.py — Pytest module covering config loader validation behavior.
│   ├── test_config_refresh.py — Pytest module covering config refresh behavior.
│   ├── test_config_service_get.py — Pytest module covering config service get behavior.
│   ├── test_daily_activity.py — Pytest module covering daily activity behavior.
│   ├── test_database_helpers.py — Pytest module covering database helpers behavior.
│   ├── test_database_migration.py — Pytest module covering database migration behavior.
│   ├── test_db_helper_extracts.py — Pytest module covering db helper extracts behavior.
│   ├── test_embeds.py — Pytest module covering embeds behavior.
│   ├── test_enhanced_workflow.py — Pytest module covering enhanced workflow behavior.
│   ├── test_ensure_verification_row.py — Pytest module covering ensure verification row behavior.
│   ├── test_error_messages.py — Pytest module covering error messages behavior.
│   ├── test_event_sync_service.py — Pytest module covering event sync service behavior.
│   ├── test_help_command.py — Pytest module covering help command behavior.
│   ├── test_helpers.py — Pytest module covering helpers behavior.
│   ├── test_info_privacy_command.py — Pytest module covering info privacy command behavior.
│   ├── test_internal_api_auth.py — Pytest module covering internal api auth behavior.
│   ├── test_internal_api_scheduled_events.py — Pytest module covering internal api scheduled events behavior.
│   ├── test_is_valid_rsi_handle_moniker.py — Pytest module covering is valid rsi handle moniker behavior.
│   ├── test_leadership_log.py — Pytest module covering leadership log behavior.
│   ├── test_metrics_activity.py — Pytest module covering metrics activity behavior.
│   ├── test_metrics_events.py — Pytest module covering metrics events behavior.
│   ├── test_metrics_service.py — Pytest module covering metrics service behavior.
│   ├── test_multi_guild_verification.py — Pytest module covering multi guild verification behavior.
│   ├── test_new_member_role.py — Pytest module covering new member role behavior.
│   ├── test_ownership_transfer_final.py — Pytest module covering ownership transfer final behavior.
│   ├── test_p0_regressions.py — Pytest module covering p0 regressions behavior.
│   ├── test_parse_rsi_org_sids.py — Pytest module covering parse rsi org sids behavior.
│   ├── test_pending_role_sync.py — Pytest module covering pending role sync behavior.
│   ├── test_permissions.py — Pytest module covering permissions behavior.
│   ├── test_rate_limiter.py — Pytest module covering rate limiter behavior.
│   ├── test_recheck_nickname_update.py — Pytest module covering recheck nickname update behavior.
│   ├── test_recheck_prune_retry.py — Pytest module covering recheck prune retry behavior.
│   ├── test_recheck_rate_limit.py — Pytest module covering recheck rate limit behavior.
│   ├── test_recheck_user_type_validation.py — Pytest module covering recheck user type validation behavior.
│   ├── test_refactored_bot.py — Pytest module covering refactored bot behavior.
│   ├── test_role_delegation_cog.py — Pytest module covering role delegation cog behavior.
│   ├── test_role_delegation_service.py — Pytest module covering role delegation service behavior.
│   ├── test_rsi_edge_cases.py — Pytest module covering rsi edge cases behavior.
│   ├── test_rsi_integration.py — Pytest module covering rsi integration behavior.
│   ├── test_rsi_live_probe.py — Pytest module covering rsi live probe behavior.
│   ├── test_rsi_verification.py — Pytest module covering rsi verification behavior.
│   ├── test_rsi_verification_moniker.py — Pytest module covering rsi verification moniker behavior.
│   ├── test_services.py — Pytest module covering services behavior.
│   ├── test_smoke.py — Pytest module covering smoke behavior.
│   ├── test_stored_settings.py — Pytest module covering stored settings behavior.
│   ├── test_task_queue_lifecycle.py — Pytest module covering task queue lifecycle behavior.
│   ├── test_task_queue_retry.py — Pytest module covering task queue retry behavior.
│   ├── test_ticket_commands.py — Pytest module covering ticket commands behavior.
│   ├── test_ticket_form_service.py — Pytest module covering ticket form service behavior.
│   ├── test_ticket_form_views.py — Pytest module covering ticket form views behavior.
│   ├── test_ticket_service.py — Pytest module covering ticket service behavior.
│   ├── test_ticket_views.py — Pytest module covering ticket views behavior.
│   ├── test_token_manager.py — Pytest module covering token manager behavior.
│   ├── test_username_404_flow.py — Pytest module covering username 404 flow behavior.
│   ├── test_verification_bulk_rsi_recheck.py — Pytest module covering verification bulk rsi recheck behavior.
│   ├── test_verification_hardening.py — Pytest module covering verification hardening behavior.
│   ├── test_verification_view_buttons.py — Pytest module covering verification view buttons behavior.
│   ├── test_verify_check_modernized.py — Pytest module covering verify check modernized behavior.
│   ├── test_views_channel_settings.py — Pytest module covering views channel settings behavior.
│   ├── test_views_db.py — Pytest module covering views db behavior.
│   ├── test_views_ui.py — Pytest module covering views ui behavior.
│   ├── test_views_verification.py — Pytest module covering views verification behavior.
│   ├── test_voice_channel_helpers.py — Pytest module covering voice channel helpers behavior.
│   ├── test_voice_claim_integration.py — Pytest module covering voice claim integration behavior.
│   ├── test_voice_cleanup.py — Pytest module covering voice cleanup behavior.
│   ├── test_voice_indexes.py — Pytest module covering voice indexes behavior.
│   ├── test_voice_integration.py — Pytest module covering voice integration behavior.
│   ├── test_voice_jtc_fixes.py — Pytest module covering voice jtc fixes behavior.
│   ├── test_voice_jtc_management.py — Pytest module covering voice jtc management behavior.
│   ├── test_voice_multiple_channels.py — Pytest module covering voice multiple channels behavior.
│   ├── test_voice_owner_command.py — Pytest module covering voice owner command behavior.
│   ├── test_voice_owner_simple.py — Pytest module covering voice owner simple behavior.
│   ├── test_voice_ownership_contract.py — Pytest module covering voice ownership contract behavior.
│   ├── test_voice_permissions.py — Pytest module covering voice permissions behavior.
│   ├── test_voice_race_conditions.py — Pytest module covering voice race conditions behavior.
│   ├── test_voice_reconciliation.py — Pytest module covering voice reconciliation behavior.
│   ├── test_voice_service_init.py — Pytest module covering voice service init behavior.
│   ├── test_voice_settings_deterministic_simple.py — Pytest module covering voice settings deterministic simple behavior.
│   ├── test_voice_settings_integration.py — Pytest module covering voice settings integration behavior.
│   ├── test_voice_state_change.py — Pytest module covering voice state change behavior.
│   ├── test_voice_strict_scoping.py — Pytest module covering voice strict scoping behavior.
│   ├── test_voice_transfer_integration.py — Pytest module covering voice transfer integration behavior.
│   └── voice_test_helpers.py — Pytest module covering voice test helpers behavior.
├── tools/ — Maintenance and diagnostic scripts.
│   ├── check_modularity.py — Python module implementing check modularity logic.
│   └── rsi_probe.py — Python module implementing rsi probe logic.
├── utils/ — Cross-cutting utility modules.
│   ├── __init__.py — Python package initializer.
│   ├── about_metadata.py — Python module implementing about metadata logic.
│   ├── log_context.py — Python module implementing log context logic.
│   ├── logging.py — Python module implementing logging logic.
│   ├── tasks.py — Python module implementing tasks logic.
│   └── types.py — Python module implementing types logic.
├── verification/ — RSI verification domain logic.
│   ├── __init__.py — Python package initializer.
│   └── rsi_verification.py — Python module implementing rsi verification logic.
├── web/ — Web dashboard backend and frontend applications.
│   ├── backend/ — FastAPI backend for dashboard and OAuth flows.
│   │   ├── .vscode/ — Subdirectory containing related project files.
│   │   │   └── settings.json — JSON configuration or schema data.
│   │   ├── core/ — Backend core services, auth, validation, and utilities.
│   │   │   ├── schemas/ — Typed schema models for backend API contracts.
│   │   │   │   ├── __init__.py — Python package initializer.
│   │   │   │   ├── auth.py — Python module implementing auth logic.
│   │   │   │   ├── errors.py — Python module implementing errors logic.
│   │   │   │   ├── events.py — Python module implementing events logic.
│   │   │   │   ├── guild.py — Python module implementing guild logic.
│   │   │   │   ├── health.py — Python module implementing health logic.
│   │   │   │   ├── metrics.py — Python module implementing metrics logic.
│   │   │   │   ├── stats.py — Python module implementing stats logic.
│   │   │   │   ├── tickets.py — Python module implementing tickets logic.
│   │   │   │   ├── users.py — Python module implementing users logic.
│   │   │   │   └── voice.py — Python module implementing voice logic.
│   │   │   ├── __init__.py — Python package initializer.
│   │   │   ├── auth.py — Python module implementing auth logic.
│   │   │   ├── dependencies.py — Python module implementing dependencies logic.
│   │   │   ├── env_config.py — Python module implementing env config logic.
│   │   │   ├── event_service.py — Python module implementing event service logic.
│   │   │   ├── guild_members.py — Python module implementing guild members logic.
│   │   │   ├── guild_settings.py — Python module implementing guild settings logic.
│   │   │   ├── internal_api_client.py — Python module implementing internal api client logic.
│   │   │   ├── log_context.py — Python module implementing log context logic.
│   │   │   ├── logo_validator.py — Python module implementing logo validator logic.
│   │   │   ├── pagination.py — Python module implementing pagination logic.
│   │   │   ├── permissions.py — Python module implementing permissions logic.
│   │   │   ├── rate_limit.py — Python module implementing rate limit logic.
│   │   │   ├── request_id.py — Python module implementing request id logic.
│   │   │   ├── rsi_utils.py — Python module implementing rsi utils logic.
│   │   │   ├── security.py — Python module implementing security logic.
│   │   │   ├── session_store.py — Python module implementing session store logic.
│   │   │   ├── user_enrichment.py — Python module implementing user enrichment logic.
│   │   │   └── validation.py — Python module implementing validation logic.
│   │   ├── routes/ — FastAPI route modules.
│   │   │   ├── __init__.py — Python package initializer.
│   │   │   ├── _metrics_helpers.py — Python module implementing metrics helpers logic.
│   │   │   ├── _ticket_helpers.py — Python module implementing ticket helpers logic.
│   │   │   ├── admin_users.py — Python module implementing admin users logic.
│   │   │   ├── auth.py — Python module implementing auth logic.
│   │   │   ├── errors.py — Python module implementing errors logic.
│   │   │   ├── guild_events.py — Python module implementing guild events logic.
│   │   │   ├── guilds.py — Python module implementing guilds logic.
│   │   │   ├── guilds_discord.py — Python module implementing guilds discord logic.
│   │   │   ├── guilds_organization.py — Python module implementing guilds organization logic.
│   │   │   ├── health.py — Python module implementing health logic.
│   │   │   ├── logs.py — Python module implementing logs logic.
│   │   │   ├── metrics.py — Python module implementing metrics logic.
│   │   │   ├── stats.py — Python module implementing stats logic.
│   │   │   ├── ticket_forms.py — Python module implementing ticket forms logic.
│   │   │   ├── tickets.py — Python module implementing tickets logic.
│   │   │   ├── users.py — Python module implementing users logic.
│   │   │   ├── users_bulk_export.py — Python module implementing users bulk export logic.
│   │   │   └── voice.py — Python module implementing voice logic.
│   │   ├── tests/ — Backend API and security tests.
│   │   │   ├── conftest.py — Pytest module covering conftest behavior.
│   │   │   ├── test_api_contract.py — Pytest module covering api contract behavior.
│   │   │   ├── test_auth.py — Pytest module covering auth behavior.
│   │   │   ├── test_bot_role_settings_delegation.py — Pytest module covering bot role settings delegation behavior.
│   │   │   ├── test_channel_settings.py — Pytest module covering channel settings behavior.
│   │   │   ├── test_config_loader.py — Pytest module covering config loader behavior.
│   │   │   ├── test_errors.py — Pytest module covering errors behavior.
│   │   │   ├── test_errors_last_admin_ok.py — Pytest module covering errors last admin ok behavior.
│   │   │   ├── test_guild_settings.py — Pytest module covering guild settings behavior.
│   │   │   ├── test_health.py — Pytest module covering health behavior.
│   │   │   ├── test_logo_validation_security.py — Pytest module covering logo validation security behavior.
│   │   │   ├── test_logs.py — Pytest module covering logs behavior.
│   │   │   ├── test_metrics_routes.py — Pytest module covering metrics routes behavior.
│   │   │   ├── test_new_member_role_settings.py — Pytest module covering new member role settings behavior.
│   │   │   ├── test_permission_hierarchy.py — Pytest module covering permission hierarchy behavior.
│   │   │   ├── test_rate_limit.py — Pytest module covering rate limit behavior.
│   │   │   ├── test_session_store.py — Pytest module covering session store behavior.
│   │   │   ├── test_stats.py — Pytest module covering stats behavior.
│   │   │   ├── test_ticket_forms_routes.py — Pytest module covering ticket forms routes behavior.
│   │   │   ├── test_tickets_routes.py — Pytest module covering tickets routes behavior.
│   │   │   ├── test_users.py — Pytest module covering users behavior.
│   │   │   ├── test_users_list.py — Pytest module covering users list behavior.
│   │   │   └── test_voice.py — Pytest module covering voice behavior.
│   │   ├── app.py — Python module implementing app logic.
│   │   └── requirements.txt — Runtime dependency list.
│   └── frontend/ — React frontend project.
│       ├── public/ — Static public assets for frontend.
│       │   └── favicon.ico — Frontend favicon asset.
│       ├── src/ — Frontend application source code.
│       │   ├── api/ — Subdirectory containing related project files.
│       │   │   ├── client.ts — TypeScript module for app logic or typings.
│       │   │   └── endpoints.ts — TypeScript module for app logic or typings.
│       │   ├── components/ — Subdirectory containing related project files.
│       │   │   ├── charts/ — Subdirectory containing related project files.
│       │   │   │   ├── GameDetailPanel.tsx — React TypeScript component module.
│       │   │   │   ├── GamePieChart.tsx — React TypeScript component module.
│       │   │   │   ├── index.ts — TypeScript module for app logic or typings.
│       │   │   │   ├── LeaderboardChart.tsx — React TypeScript component module.
│       │   │   │   ├── MetricCard.tsx — React TypeScript component module.
│       │   │   │   ├── TimeSeriesChart.tsx — React TypeScript component module.
│       │   │   │   └── UserDetailPanel.tsx — React TypeScript component module.
│       │   │   ├── layout/ — Subdirectory containing related project files.
│       │   │   │   ├── ActionSheet.tsx — React TypeScript component module.
│       │   │   │   ├── DashboardShell.test.tsx — React TypeScript component module.
│       │   │   │   ├── DashboardShell.tsx — React TypeScript component module.
│       │   │   │   ├── index.ts — TypeScript module for app logic or typings.
│       │   │   │   ├── MobileNav.tsx — React TypeScript component module.
│       │   │   │   ├── PageHeader.tsx — React TypeScript component module.
│       │   │   │   └── ResponsiveTable.tsx — React TypeScript component module.
│       │   │   ├── metrics/ — Subdirectory containing related project files.
│       │   │   │   └── UserMetricsPanel.tsx — React TypeScript component module.
│       │   │   ├── ui/ — Subdirectory containing related project files.
│       │   │   │   ├── Alert.tsx — React TypeScript component module.
│       │   │   │   ├── Badge.tsx — React TypeScript component module.
│       │   │   │   ├── Button.tsx — React TypeScript component module.
│       │   │   │   ├── Card.tsx — React TypeScript component module.
│       │   │   │   ├── index.ts — TypeScript module for app logic or typings.
│       │   │   │   ├── Input.tsx — React TypeScript component module.
│       │   │   │   ├── Modal.tsx — React TypeScript component module.
│       │   │   │   ├── Pagination.tsx — React TypeScript component module.
│       │   │   │   ├── Spinner.tsx — React TypeScript component module.
│       │   │   │   └── Table.tsx — React TypeScript component module.
│       │   │   ├── users/ — Subdirectory containing related project files.
│       │   │   │   ├── OrgBadgeList.tsx — React TypeScript component module.
│       │   │   │   └── UserDetailsModal.tsx — React TypeScript component module.
│       │   │   ├── AccordionSection.tsx — React TypeScript component module.
│       │   │   ├── BulkRecheckIntegrationExample.tsx — React TypeScript component module.
│       │   │   ├── BulkRecheckResultsModal.tsx — React TypeScript component module.
│       │   │   ├── DiscordMarkdownEditor.test.tsx — React TypeScript component module.
│       │   │   ├── DiscordMarkdownEditor.tsx — React TypeScript component module.
│       │   │   ├── SearchableMultiSelect.tsx — React TypeScript component module.
│       │   │   ├── SearchableSelect.test.tsx — React TypeScript component module.
│       │   │   └── SearchableSelect.tsx — React TypeScript component module.
│       │   ├── contexts/ — Subdirectory containing related project files.
│       │   │   └── AuthContext.tsx — React TypeScript component module.
│       │   ├── hooks/ — Subdirectory containing related project files.
│       │   │   ├── useClickOutside.ts — TypeScript module for app logic or typings.
│       │   │   ├── useGameMetrics.test.tsx — React TypeScript component module.
│       │   │   ├── useGameMetrics.ts — TypeScript module for app logic or typings.
│       │   │   ├── useMediaQuery.ts — TypeScript module for app logic or typings.
│       │   │   ├── useRequestSequence.test.tsx — React TypeScript component module.
│       │   │   ├── useRequestSequence.ts — TypeScript module for app logic or typings.
│       │   │   ├── useUserMetrics.test.tsx — React TypeScript component module.
│       │   │   └── useUserMetrics.ts — TypeScript module for app logic or typings.
│       │   ├── pages/ — Subdirectory containing related project files.
│       │   │   ├── tickets/ — Subdirectory containing related project files.
│       │   │   │   ├── CategoryModal.tsx — React TypeScript component module.
│       │   │   │   ├── ChannelAddModal.tsx — React TypeScript component module.
│       │   │   │   ├── ChannelSection.tsx — React TypeScript component module.
│       │   │   │   ├── constants.ts — TypeScript module for app logic or typings.
│       │   │   │   ├── DeleteCategoryModal.tsx — React TypeScript component module.
│       │   │   │   ├── FormEditorModal.tsx — React TypeScript component module.
│       │   │   │   ├── index.ts — TypeScript module for app logic or typings.
│       │   │   │   ├── PanelPreview.tsx — React TypeScript component module.
│       │   │   │   ├── TicketList.tsx — React TypeScript component module.
│       │   │   │   ├── TicketStats.tsx — React TypeScript component module.
│       │   │   │   └── utils.ts — TypeScript module for app logic or typings.
│       │   │   ├── Dashboard.test.tsx — React TypeScript component module.
│       │   │   ├── Dashboard.tsx — React TypeScript component module.
│       │   │   ├── DashboardBotSettings.tsx — React TypeScript component module.
│       │   │   ├── EventEditor.test.tsx — React TypeScript component module.
│       │   │   ├── EventEditor.tsx — React TypeScript component module.
│       │   │   ├── eventFlowShared.ts — TypeScript module for app logic or typings.
│       │   │   ├── Events.test.tsx — React TypeScript component module.
│       │   │   ├── Events.tsx — React TypeScript component module.
│       │   │   ├── Landing.test.tsx — React TypeScript component module.
│       │   │   ├── Landing.tsx — React TypeScript component module.
│       │   │   ├── Metrics.test.tsx — React TypeScript component module.
│       │   │   ├── Metrics.tsx — React TypeScript component module.
│       │   │   ├── SelectServer.tsx — React TypeScript component module.
│       │   │   ├── Tickets.tsx — React TypeScript component module.
│       │   │   ├── Users.test.tsx — React TypeScript component module.
│       │   │   ├── Users.tsx — React TypeScript component module.
│       │   │   ├── Voice.test.tsx — React TypeScript component module.
│       │   │   └── Voice.tsx — React TypeScript component module.
│       │   ├── utils/ — Subdirectory containing related project files.
│       │   │   ├── chartStyles.ts — TypeScript module for app logic or typings.
│       │   │   ├── cn.ts — TypeScript module for app logic or typings.
│       │   │   ├── download.ts — TypeScript module for app logic or typings.
│       │   │   ├── format.ts — TypeScript module for app logic or typings.
│       │   │   ├── permissions.test.ts — TypeScript module for app logic or typings.
│       │   │   ├── permissions.ts — TypeScript module for app logic or typings.
│       │   │   ├── statusHelpers.ts — TypeScript module for app logic or typings.
│       │   │   ├── theme.ts — TypeScript module for app logic or typings.
│       │   │   ├── tierColors.ts — TypeScript module for app logic or typings.
│       │   │   ├── tierHelpers.ts — TypeScript module for app logic or typings.
│       │   │   └── toast.ts — TypeScript module for app logic or typings.
│       │   ├── App.test.tsx — React TypeScript component module.
│       │   ├── App.tsx — React TypeScript component module.
│       │   ├── index.css — CSS stylesheet for frontend styling.
│       │   ├── main.tsx — React TypeScript component module.
│       │   └── vite-env.d.ts — TypeScript module for app logic or typings.
│       ├── index.html — HTML template or sample fixture file.
│       ├── package-lock.json — JSON configuration or schema data.
│       ├── package.json — JSON configuration or schema data.
│       ├── postcss.config.js — JavaScript configuration or utility script.
│       ├── tailwind.config.js — JavaScript configuration or utility script.
│       ├── tsconfig.json — JSON configuration or schema data.
│       ├── tsconfig.node.json — JSON configuration or schema data.
│       ├── vite.config.ts — TypeScript module for app logic or typings.
│       └── vitest.config.ts — TypeScript module for app logic or typings.
├── .editorconfig — Cross-editor formatting defaults.
├── .env.example — Example environment variables for local setup.
├── .gitattributes — Git attribute behavior configuration.
├── .gitignore — Ignore rules for untracked/generated files.
├── .pre-commit-config.yaml — Pre-commit hook and quality gate configuration.
├── .python-version — Pinned local Python interpreter version.
├── bot.py — Main Discord bot runtime entrypoint.
├── bot.pyi — Type stubs for bot interfaces and attributes.
├── bot_tasks.py — Background task helpers for bot workflows.
├── CLAUDE.md — Contributor-agent guidance for this repository.
├── CONTRIBUTING.md — Contribution workflow and repository standards.
├── discord-bot.code-workspace — VS Code workspace definition.
├── LICENSE — Project license terms.
├── PRIVACY.md — Privacy and data-handling policy.
├── pyproject.toml — Python tooling, lint, and type-check configuration.
├── pytest.ini — Pytest execution configuration.
├── README.md — Primary project overview and navigation.
├── requirements-dev.txt — Development dependency locklist.
├── requirements.txt — Runtime dependency list.
├── SECURITY.md — Security policy and disclosure process.
├── SETUP.md — Deployment and setup instructions.
├── start_bot.py — Startup wrapper for launching the bot.
└── VS_CODE_SETUP.md — VS Code setup and debugging guide.
```
