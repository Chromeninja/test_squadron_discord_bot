# Repository Documents

This folder centralizes repository-level documentation to keep project guidance easy to find and maintain.

## Documentation standards

- Keep documents focused on one topic.
- Use clear section headings and predictable file names.
- Prefer relative links between documents.
- Update related docs in the same PR when structure changes.
- Keep architecture and file layout docs current with the codebase.

## Documents in this folder

- [`SETUP.md`](./SETUP.md): Deployment guide — Docker Compose (recommended) and the manual systemd/nginx alternative.
- [`VS_CODE_SETUP.md`](./VS_CODE_SETUP.md): Local development setup and full-stack Docker testing from VS Code.
- [`backend-first-migration.md`](./backend-first-migration.md): Backend-first architecture migration roadmap and current status.
- [`file-map.md`](./file-map.md): Directory-by-directory map of the repository with key purpose notes and file inventory.

> GitHub-surfaced files (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `PRIVACY.md`, `CLAUDE.md`) intentionally stay at the repository root so GitHub renders them in the expected places.

## Maintenance checklist

When adding, removing, or moving files/folders:

1. Update `documents/file-map.md`.
2. Update any referenced setup/architecture docs (`README.md`, `documents/SETUP.md`, `documents/VS_CODE_SETUP.md`) if impacted.
3. Keep document links valid and relative.
