# System Overview

```mermaid
flowchart LR
  Discord[Discord Gateway] --> Bot[Discord bot\nbot.py and cogs]
  Bot --> Connectors[Typed connectors]
  Connectors --> API[FastAPI backend]
  Dashboard[React dashboard] --> Web[Dashboard FastAPI]
  Web --> API
  API --> Repo[Backend repositories]
  Repo --> DB[(SQLite)]
  Web --> OAuth[Discord OAuth2]
```

The backend is the authoritative data and API boundary. New guild-scoped data
access belongs in `backend/db/repository/`; bot code accesses it through
`connectors/` and the dashboard uses its existing backend routes.
