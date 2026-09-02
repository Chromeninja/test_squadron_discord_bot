# Maintainer Guide

## Review expectations

Every change should have a clear scope, tests for behavior changes, and
documentation for user-visible or operational changes. Review permission,
privacy, guild-isolation, and secret-handling impact explicitly.

Use the checks in [`CONTRIBUTING.md`](../CONTRIBUTING.md). Changes crossing
process or data boundaries must also follow
[`backend-first-migration.md`](backend-first-migration.md).

## Release checklist

1. Run the Python and frontend test, lint, format, and type checks.
2. Review dependency and security alerts.
3. Update `pyproject.toml` and `CHANGELOG.md`.
4. Verify `.env.example`, `config/config-example.yaml`, and deployment docs.
5. Build both Docker images and verify the backend health endpoint.
6. Back up SQLite data before production deployment.
7. Tag the release and publish release notes.

## Incident basics

For a suspected security issue, preserve relevant logs without exposing secrets,
limit access, and follow `SECURITY.md`. For data incidents, stop destructive
operations, preserve a backup, and document the affected guild scope and time
window.
