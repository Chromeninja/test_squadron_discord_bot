# TEST Squadron Discord Bot — Server Setup (Linux)

Use this guide to deploy the full stack on a Linux host: Discord bot, Web Admin backend (FastAPI), and Web Admin frontend (Vite).

## Prerequisites
- Python 3.8+
- Git
- Node.js 18+ + npm
- Discord Bot token
- Discord OAuth app credentials (client id/secret/redirect URI)

## 1) Clone repo
```bash
git clone https://github.com/Chromeninja/test_squadron_discord_bot.git test_discord_bot
cd test_discord_bot
```

## 2) Create + activate venv
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Install Python deps (bot + backend + dev tooling)
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r web/backend/requirements.txt
pip install -r requirements-dev.txt
```

## 4) Install + build frontend deps
```bash
cd web/frontend
npm install
npm run build
cd ../..
```

## 5) Configure environment
Create/merge `.env` in project root (used by bot and backend):
```bash
nano .env
```
Example:
```env
# Discord Bot
DISCORD_TOKEN=your_bot_token_here

# Database
DB_PATH=./test_squadron.db

# Web Admin OAuth
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here
DISCORD_REDIRECT_URI=http://localhost:8081/auth/callback
SESSION_SECRET=change_me_to_a_long_random_string_min_32_chars

# Frontend -> Backend
VITE_API_BASE=http://localhost:8081

ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

## 6) YAML config
- Global config lives at `config/config.yaml`.
- Use `config/config-example.yaml` as a reference if you need to regenerate.

## 7) Run the full stack (manual terminals)
Open three terminals (all from repo root, with `.venv` active):

**Terminal 1 — Backend (FastAPI)**
```bash
source .venv/bin/activate
.venv/bin/python -m uvicorn app:app --app-dir web/backend \
  --host 0.0.0.0 --port 8081 --reload
```

**Terminal 2 — Frontend (Vite dev)**
```bash
cd web/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

**Terminal 3 — Discord bot**
```bash
source .venv/bin/activate
python bot.py
```

> All three services must run together for a working system.

## 8) Quick checks
- Bot: run `/status` in Discord and expect a response
- Backend: http://localhost:8081/docs (FastAPI Swagger UI)
- Frontend: http://localhost:5173 (Vite dev server)
- OAuth login works and dashboard loads

## 9) Testing
```bash
.venv/bin/python -m pytest tests/ web/backend/tests/ -v
```

## Notes
- If the venv is not activated, prefix commands with `.venv/bin/python`.
- Stop services before pulling updates or migrating the database.
- If frontend assets change, rebuild with `npm run build` (and rerun `npm run dev` or `npm run preview`).
