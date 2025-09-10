This folder contains VS Code workspace settings tuned for automated test runs and AI agents.

What it does:
- Sets the Python interpreter to `${workspaceFolder}/.venv/bin/python`.
- Configures pytest to use the project's `.venv/bin/pytest` binary for consistent runs.
- Enables auto test discovery on save so agents and CI can pick up tests quickly.
- Exposes the venv on PATH for integrated terminals and tools.

If your venv is named differently, update `.vscode/settings.json` and `.env` accordingly.
