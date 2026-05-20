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
## Full recursive tree (generated)

```text
test_squadron_discord_bot/
├── .github/
│   ├── codeql/
│   │   └── codeql-config.yml
│   ├── instructions/
│   │   ├── database.instructions.md
│   │   ├── python.instructions.md
│   │   └── tests.instructions.md
│   ├── skills/
│   │   ├── gh-pr-edit/
│   │   │   └── SKILL.md
│   │   ├── github-issue-tracking/
│   │   │   └── SKILL.md
│   │   ├── pre-commit-checks/
│   │   │   └── SKILL.md
│   │   └── security-scan/
│   │       └── SKILL.md
│   ├── workflows/
│   │   ├── codeql.yml
│   │   └── tests.yml
│   ├── copilot-instructions.md
│   └── dependabot.yml
├── .vscode/
│   ├── extensions.json
│   ├── launch.json
│   ├── README.md
│   ├── settings.json
│   └── tasks.json
├── cogs/
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── check_user.py
│   │   ├── commands.py
│   │   ├── member_lifecycle.py
│   │   ├── new_member_role_worker.py
│   │   ├── recheck.py
│   │   ├── role_delegation.py
│   │   └── verify_bulk.py
│   ├── info/
│   │   ├── __init__.py
│   │   ├── about.py
│   │   ├── dashboard.py
│   │   ├── help.py
│   │   └── privacy.py
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── events.py
│   ├── tickets/
│   │   ├── __init__.py
│   │   └── commands.py
│   ├── verification/
│   │   ├── __init__.py
│   │   └── commands.py
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── commands.py
│   │   ├── events.py
│   │   └── service_bridge.py
│   └── __init__.py
├── config/
│   ├── __init__.py
│   ├── config-example.yaml
│   └── config_loader.py
├── documents/
│   ├── file-map.md
│   └── README.md
├── helpers/
│   ├── __init__.py
│   ├── announcement.py
│   ├── announcement_bulk_cog.py
│   ├── audit.py
│   ├── bot_protocol.py
│   ├── bot_utils.py
│   ├── bulk_check.py
│   ├── circuit_breaker.py
│   ├── cog_loader.py
│   ├── constants.py
│   ├── daily_activity_tracker.py
│   ├── decorators.py
│   ├── discord_api.py
│   ├── discord_reply.py
│   ├── embeds.py
│   ├── embeds_factory.py
│   ├── embeds_voice.py
│   ├── error_messages.py
│   ├── http_helper.py
│   ├── leadership_log.py
│   ├── leadership_log_models.py
│   ├── modals.py
│   ├── permissions_helper.py
│   ├── rate_limiter.py
│   ├── recheck_service.py
│   ├── role_helper.py
│   ├── role_ids.py
│   ├── role_select_utils.py
│   ├── secure_random.py
│   ├── snapshots.py
│   ├── task_queue.py
│   ├── ticket_form_views.py
│   ├── ticket_views.py
│   ├── ticket_views_action.py
│   ├── ticket_views_helpers.py
│   ├── ticket_views_thread.py
│   ├── token_manager.py
│   ├── username_404.py
│   ├── verification_logging.py
│   ├── verification_messages.py
│   ├── views.py
│   ├── views_admin.py
│   ├── views_feature.py
│   ├── views_verification.py
│   ├── views_voice.py
│   ├── voice_permissions.py
│   ├── voice_repo.py
│   ├── voice_settings.py
│   └── voice_utils.py
├── prompts/
│   ├── messages/
│   │   └── verification.md
│   ├── schemas/
│   │   ├── api_responses.json
│   │   ├── database_models.json
│   │   └── discord_events.json
│   ├── system/
│   │   ├── development_guide.md
│   │   └── error_analysis.md
│   └── README.md
├── services/
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── managed_event_mapper.py
│   │   ├── membership.py
│   │   ├── metrics_db.py
│   │   ├── repository.py
│   │   └── schema.py
│   ├── __init__.py
│   ├── base.py
│   ├── config_service.py
│   ├── event_sync_service.py
│   ├── guild_config_helper.py
│   ├── guild_service.py
│   ├── guild_sync.py
│   ├── health_service.py
│   ├── internal_api.py
│   ├── internal_api_metrics_mixin.py
│   ├── log_cleanup.py
│   ├── metrics_activity.py
│   ├── metrics_buckets.py
│   ├── metrics_flush.py
│   ├── metrics_models.py
│   ├── metrics_queries.py
│   ├── metrics_read.py
│   ├── metrics_service.py
│   ├── new_member_role_service.py
│   ├── role_delegation_service.py
│   ├── service_container.py
│   ├── ticket_form_service.py
│   ├── ticket_rate_limiter.py
│   ├── ticket_service.py
│   ├── verification_bulk_service.py
│   ├── verification_scheduler.py
│   ├── verification_state.py
│   ├── voice_base_mixin.py
│   ├── voice_channel_helpers.py
│   ├── voice_channel_mixin.py
│   ├── voice_create_mixin.py
│   ├── voice_jtc_mixin.py
│   ├── voice_reconcile_mixin.py
│   ├── voice_service.py
│   ├── voice_settings_mixin.py
│   ├── voice_setup_mixin.py
│   └── voice_state_mixin.py
├── tests/
│   ├── factories/
│   │   ├── __init__.py
│   │   ├── config_factories.py
│   │   ├── db_factories.py
│   │   ├── discord_factories.py
│   │   └── html_factories.py
│   ├── permissions/
│   │   └── test_permissions_helper.py
│   ├── roles/
│   │   └── test_role_select_utils.py
│   ├── services/
│   │   └── test_voice_service.py
│   ├── conftest.py
│   ├── sample_rsi_organizations.html
│   ├── sample_rsi_profile.html
│   ├── test_admin_list_functionality.py
│   ├── test_admin_recheck_updates.py
│   ├── test_admin_status.py
│   ├── test_announcement_helpers.py
│   ├── test_announcement_logic.py
│   ├── test_bot_startup.py
│   ├── test_bulk_check.py
│   ├── test_check_user_activity.py
│   ├── test_circuit_breaker.py
│   ├── test_command_handlers.py
│   ├── test_config_loader_validation.py
│   ├── test_config_refresh.py
│   ├── test_config_service_get.py
│   ├── test_daily_activity.py
│   ├── test_database_helpers.py
│   ├── test_database_migration.py
│   ├── test_db_helper_extracts.py
│   ├── test_embeds.py
│   ├── test_enhanced_workflow.py
│   ├── test_ensure_verification_row.py
│   ├── test_error_messages.py
│   ├── test_event_sync_service.py
│   ├── test_help_command.py
│   ├── test_helpers.py
│   ├── test_info_privacy_command.py
│   ├── test_internal_api_auth.py
│   ├── test_internal_api_scheduled_events.py
│   ├── test_is_valid_rsi_handle_moniker.py
│   ├── test_leadership_log.py
│   ├── test_metrics_activity.py
│   ├── test_metrics_events.py
│   ├── test_metrics_service.py
│   ├── test_multi_guild_verification.py
│   ├── test_new_member_role.py
│   ├── test_ownership_transfer_final.py
│   ├── test_p0_regressions.py
│   ├── test_parse_rsi_org_sids.py
│   ├── test_pending_role_sync.py
│   ├── test_permissions.py
│   ├── test_rate_limiter.py
│   ├── test_recheck_nickname_update.py
│   ├── test_recheck_prune_retry.py
│   ├── test_recheck_rate_limit.py
│   ├── test_recheck_user_type_validation.py
│   ├── test_refactored_bot.py
│   ├── test_role_delegation_cog.py
│   ├── test_role_delegation_service.py
│   ├── test_rsi_edge_cases.py
│   ├── test_rsi_integration.py
│   ├── test_rsi_live_probe.py
│   ├── test_rsi_verification.py
│   ├── test_rsi_verification_moniker.py
│   ├── test_services.py
│   ├── test_smoke.py
│   ├── test_stored_settings.py
│   ├── test_task_queue_lifecycle.py
│   ├── test_task_queue_retry.py
│   ├── test_ticket_commands.py
│   ├── test_ticket_form_service.py
│   ├── test_ticket_form_views.py
│   ├── test_ticket_service.py
│   ├── test_ticket_views.py
│   ├── test_token_manager.py
│   ├── test_username_404_flow.py
│   ├── test_verification_bulk_rsi_recheck.py
│   ├── test_verification_hardening.py
│   ├── test_verification_view_buttons.py
│   ├── test_verify_check_modernized.py
│   ├── test_views_channel_settings.py
│   ├── test_views_db.py
│   ├── test_views_ui.py
│   ├── test_views_verification.py
│   ├── test_voice_channel_helpers.py
│   ├── test_voice_claim_integration.py
│   ├── test_voice_cleanup.py
│   ├── test_voice_indexes.py
│   ├── test_voice_integration.py
│   ├── test_voice_jtc_fixes.py
│   ├── test_voice_jtc_management.py
│   ├── test_voice_multiple_channels.py
│   ├── test_voice_owner_command.py
│   ├── test_voice_owner_simple.py
│   ├── test_voice_ownership_contract.py
│   ├── test_voice_permissions.py
│   ├── test_voice_race_conditions.py
│   ├── test_voice_reconciliation.py
│   ├── test_voice_service_init.py
│   ├── test_voice_settings_deterministic_simple.py
│   ├── test_voice_settings_integration.py
│   ├── test_voice_state_change.py
│   ├── test_voice_strict_scoping.py
│   ├── test_voice_transfer_integration.py
│   └── voice_test_helpers.py
├── tools/
│   ├── check_modularity.py
│   └── rsi_probe.py
├── utils/
│   ├── __init__.py
│   ├── about_metadata.py
│   ├── log_context.py
│   ├── logging.py
│   ├── tasks.py
│   └── types.py
├── verification/
│   ├── __init__.py
│   └── rsi_verification.py
├── web/
│   ├── backend/
│   │   ├── .vscode/
│   │   │   └── settings.json
│   │   ├── core/
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── errors.py
│   │   │   │   ├── events.py
│   │   │   │   ├── guild.py
│   │   │   │   ├── health.py
│   │   │   │   ├── metrics.py
│   │   │   │   ├── stats.py
│   │   │   │   ├── tickets.py
│   │   │   │   ├── users.py
│   │   │   │   └── voice.py
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── dependencies.py
│   │   │   ├── env_config.py
│   │   │   ├── event_service.py
│   │   │   ├── guild_members.py
│   │   │   ├── guild_settings.py
│   │   │   ├── internal_api_client.py
│   │   │   ├── log_context.py
│   │   │   ├── logo_validator.py
│   │   │   ├── pagination.py
│   │   │   ├── permissions.py
│   │   │   ├── rate_limit.py
│   │   │   ├── request_id.py
│   │   │   ├── rsi_utils.py
│   │   │   ├── security.py
│   │   │   ├── session_store.py
│   │   │   ├── user_enrichment.py
│   │   │   └── validation.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── _metrics_helpers.py
│   │   │   ├── _ticket_helpers.py
│   │   │   ├── admin_users.py
│   │   │   ├── auth.py
│   │   │   ├── errors.py
│   │   │   ├── guild_events.py
│   │   │   ├── guilds.py
│   │   │   ├── guilds_discord.py
│   │   │   ├── guilds_organization.py
│   │   │   ├── health.py
│   │   │   ├── logs.py
│   │   │   ├── metrics.py
│   │   │   ├── stats.py
│   │   │   ├── ticket_forms.py
│   │   │   ├── tickets.py
│   │   │   ├── users.py
│   │   │   ├── users_bulk_export.py
│   │   │   └── voice.py
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── test_api_contract.py
│   │   │   ├── test_auth.py
│   │   │   ├── test_bot_role_settings_delegation.py
│   │   │   ├── test_channel_settings.py
│   │   │   ├── test_config_loader.py
│   │   │   ├── test_errors.py
│   │   │   ├── test_errors_last_admin_ok.py
│   │   │   ├── test_guild_settings.py
│   │   │   ├── test_health.py
│   │   │   ├── test_logo_validation_security.py
│   │   │   ├── test_logs.py
│   │   │   ├── test_metrics_routes.py
│   │   │   ├── test_new_member_role_settings.py
│   │   │   ├── test_permission_hierarchy.py
│   │   │   ├── test_rate_limit.py
│   │   │   ├── test_session_store.py
│   │   │   ├── test_stats.py
│   │   │   ├── test_ticket_forms_routes.py
│   │   │   ├── test_tickets_routes.py
│   │   │   ├── test_users.py
│   │   │   ├── test_users_list.py
│   │   │   └── test_voice.py
│   │   ├── app.py
│   │   └── requirements.txt
│   └── frontend/
│       ├── public/
│       │   └── favicon.ico
│       ├── src/
│       │   ├── api/
│       │   │   ├── client.ts
│       │   │   └── endpoints.ts
│       │   ├── components/
│       │   │   ├── charts/
│       │   │   │   ├── GameDetailPanel.tsx
│       │   │   │   ├── GamePieChart.tsx
│       │   │   │   ├── index.ts
│       │   │   │   ├── LeaderboardChart.tsx
│       │   │   │   ├── MetricCard.tsx
│       │   │   │   ├── TimeSeriesChart.tsx
│       │   │   │   └── UserDetailPanel.tsx
│       │   │   ├── layout/
│       │   │   │   ├── ActionSheet.tsx
│       │   │   │   ├── DashboardShell.test.tsx
│       │   │   │   ├── DashboardShell.tsx
│       │   │   │   ├── index.ts
│       │   │   │   ├── MobileNav.tsx
│       │   │   │   ├── PageHeader.tsx
│       │   │   │   └── ResponsiveTable.tsx
│       │   │   ├── metrics/
│       │   │   │   └── UserMetricsPanel.tsx
│       │   │   ├── ui/
│       │   │   │   ├── Alert.tsx
│       │   │   │   ├── Badge.tsx
│       │   │   │   ├── Button.tsx
│       │   │   │   ├── Card.tsx
│       │   │   │   ├── index.ts
│       │   │   │   ├── Input.tsx
│       │   │   │   ├── Modal.tsx
│       │   │   │   ├── Pagination.tsx
│       │   │   │   ├── Spinner.tsx
│       │   │   │   └── Table.tsx
│       │   │   ├── users/
│       │   │   │   ├── OrgBadgeList.tsx
│       │   │   │   └── UserDetailsModal.tsx
│       │   │   ├── AccordionSection.tsx
│       │   │   ├── BulkRecheckIntegrationExample.tsx
│       │   │   ├── BulkRecheckResultsModal.tsx
│       │   │   ├── DiscordMarkdownEditor.test.tsx
│       │   │   ├── DiscordMarkdownEditor.tsx
│       │   │   ├── SearchableMultiSelect.tsx
│       │   │   ├── SearchableSelect.test.tsx
│       │   │   └── SearchableSelect.tsx
│       │   ├── contexts/
│       │   │   └── AuthContext.tsx
│       │   ├── hooks/
│       │   │   ├── useClickOutside.ts
│       │   │   ├── useGameMetrics.test.tsx
│       │   │   ├── useGameMetrics.ts
│       │   │   ├── useMediaQuery.ts
│       │   │   ├── useRequestSequence.test.tsx
│       │   │   ├── useRequestSequence.ts
│       │   │   ├── useUserMetrics.test.tsx
│       │   │   └── useUserMetrics.ts
│       │   ├── pages/
│       │   │   ├── tickets/
│       │   │   │   ├── CategoryModal.tsx
│       │   │   │   ├── ChannelAddModal.tsx
│       │   │   │   ├── ChannelSection.tsx
│       │   │   │   ├── constants.ts
│       │   │   │   ├── DeleteCategoryModal.tsx
│       │   │   │   ├── FormEditorModal.tsx
│       │   │   │   ├── index.ts
│       │   │   │   ├── PanelPreview.tsx
│       │   │   │   ├── TicketList.tsx
│       │   │   │   ├── TicketStats.tsx
│       │   │   │   └── utils.ts
│       │   │   ├── Dashboard.test.tsx
│       │   │   ├── Dashboard.tsx
│       │   │   ├── DashboardBotSettings.tsx
│       │   │   ├── EventEditor.test.tsx
│       │   │   ├── EventEditor.tsx
│       │   │   ├── eventFlowShared.ts
│       │   │   ├── Events.test.tsx
│       │   │   ├── Events.tsx
│       │   │   ├── Landing.test.tsx
│       │   │   ├── Landing.tsx
│       │   │   ├── Metrics.test.tsx
│       │   │   ├── Metrics.tsx
│       │   │   ├── SelectServer.tsx
│       │   │   ├── Tickets.tsx
│       │   │   ├── Users.test.tsx
│       │   │   ├── Users.tsx
│       │   │   ├── Voice.test.tsx
│       │   │   └── Voice.tsx
│       │   ├── utils/
│       │   │   ├── chartStyles.ts
│       │   │   ├── cn.ts
│       │   │   ├── download.ts
│       │   │   ├── format.ts
│       │   │   ├── permissions.test.ts
│       │   │   ├── permissions.ts
│       │   │   ├── statusHelpers.ts
│       │   │   ├── theme.ts
│       │   │   ├── tierColors.ts
│       │   │   ├── tierHelpers.ts
│       │   │   └── toast.ts
│       │   ├── App.test.tsx
│       │   ├── App.tsx
│       │   ├── index.css
│       │   ├── main.tsx
│       │   └── vite-env.d.ts
│       ├── index.html
│       ├── package-lock.json
│       ├── package.json
│       ├── postcss.config.js
│       ├── tailwind.config.js
│       ├── tsconfig.json
│       ├── tsconfig.node.json
│       ├── vite.config.ts
│       └── vitest.config.ts
├── .editorconfig
├── .env.example
├── .gitattributes
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── bot.py
├── bot.pyi
├── bot_tasks.py
├── CLAUDE.md
├── CONTRIBUTING.md
├── discord-bot.code-workspace
├── LICENSE
├── PRIVACY.md
├── pyproject.toml
├── pytest.ini
├── README.md
├── requirements-dev.txt
├── requirements.txt
├── SECURITY.md
├── SETUP.md
├── start_bot.py
└── VS_CODE_SETUP.md
```
