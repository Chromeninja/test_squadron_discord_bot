# TEST Squadron Discord Bot — Server Setup (Linux)

Use this guide to deploy the full stack on a Linux host: Discord bot, Web Admin backend (FastAPI), and Web Admin frontend (Vite).

## Prerequisites
- Python 3.12+ (recommended) with `venv`
- Git
- Node.js 20+ and npm (for frontend and tests)
- Discord Bot token
- Discord OAuth app credentials (client id/secret/redirect URI)

### Developer tools (new)
- Frontend test runner: Vitest (installed via `npm install`)
- DOM environment for tests: `happy-dom` (auto-installed via `npm install -D happy-dom`)
- Optional: `jsdom` if you prefer, but `happy-dom` is configured by default in `vite.config.ts`
- Python test tools: `pytest`, `pytest-asyncio` (from `requirements-dev.txt`)

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

Frontend tests (optional, recommended for UI changes):
```bash
cd web/frontend
npm test -- --run
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

## 7) Run as systemd services (production / cloud)

> On a server you should NOT keep 3 terminals open.
> Instead, run the **backend + bot as services**, and serve the **frontend as static files**.

### 7.1 Backend service (FastAPI)

1. Create a systemd unit:

```bash
sudo nano /etc/systemd/system/test_squadron_backend.service
```
Paste this (edit `User` and paths if your home dir differs):

```ini
[Unit]
Description=TEST Squadron Web Admin Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=chrome
WorkingDirectory=/home/chrome/test_squadron_discord_bot
EnvironmentFile=/home/chrome/test_squadron_discord_bot/.env
ExecStart=/home/chrome/test_squadron_discord_bot/.venv/bin/python -m uvicorn app:app --app-dir web/backend --host 0.0.0.0 --port 8081
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable + start it:

```bash
sudo systemctl daemon-reload
sudo systemctl start test_squadron_backend.service
sudo systemctl enable test_squadron_backend.service
```

### 7.2 Discord bot service

Create a systemd unit:

```bash
sudo nano /etc/systemd/system/test_squadron_bot.service
```
Paste this:

```ini
[Unit]
Description=TEST Squadron Discord Bot
After=network.target

[Service]
Type=simple
User=chrome
WorkingDirectory=/home/chrome/test_squadron_discord_bot
EnvironmentFile=/home/chrome/test_squadron_discord_bot/.env
ExecStart=/home/chrome/test_squadron_discord_bot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable + start it:

```bash
sudo systemctl daemon-reload
sudo systemctl start test_squadron_bot.service
sudo systemctl enable test_squadron_bot.service
```

### 7.3 Frontend in production (static)

In production you do not run `npm run dev`.
You already built the frontend in step 4. Serve the built files (the `dist` folder) with a web server.

```bash
web/frontend/dist
```

Serve that folder with a web server (nginx/caddy/apache). Make sure your domain proxies `/api` to the backend on port `8081`.

### 7.4 Useful service commands

Check status:

```bash
sudo systemctl status test_squadron_backend.service
sudo systemctl status test_squadron_bot.service
```

Restart after updates:

```bash
sudo systemctl restart test_squadron_backend.service
sudo systemctl restart test_squadron_bot.service
```

Follow logs:

```bash
sudo journalctl -u test_squadron_backend.service -f
sudo journalctl -u test_squadron_bot.service -f
```

Stop services before migrations/updates:

```bash
sudo systemctl stop test_squadron_backend.service
sudo systemctl stop test_squadron_bot.service
```

## 8) Expose the backend/bot on a Vultr VM (public/LAN access)

The backend listens on port 8081 and the bot’s internal API (if enabled) often on 8082. Use a reverse proxy with TLS for public access; only expose raw ports when necessary.

1. Bind services to all interfaces (already set to `--host 0.0.0.0`).
2. Open firewall (Ubuntu `ufw` example):
   ```bash
   sudo ufw allow OpenSSH
   sudo ufw allow 80/tcp   # HTTP (for ACME) if using a proxy
   sudo ufw allow 443/tcp  # HTTPS
   # Optional: expose backend directly (not recommended publicly)
   # sudo ufw allow 8081/tcp
   # Optional: expose bot internal API; prefer restricting to trusted IPs
   # sudo ufw allow from <YOUR_IP> to any port 8082 proto tcp
   sudo ufw enable
   ```
   If Vultr cloud firewall is enabled, mirror these rules there (80, 443, and only the ports you truly need).
3. Reverse proxy with TLS (recommended). Example Caddyfile:
   ```
   your-domain.example.com {
     reverse_proxy localhost:8081
   }
   ```
   Or Nginx (snippet):
   ```
   server {
     listen 80;
     server_name your-domain.example.com;
     location / {
       proxy_pass http://127.0.0.1:8081;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
     }
   }
   ```
   Add HTTPS with Let’s Encrypt (e.g., `certbot --nginx -d your-domain.example.com`).
4. Point DNS to your Vultr VM public IP (A record). Test from another device: `curl -I https://your-domain.example.com/api/health`.
5. Lock down the bot internal API:
   - Prefer keeping it private or behind firewall allowlists.
   - If you must expose, require auth (API key) and consider a separate hostname/port with allowlisted IPs.

Tip: On a LAN-only test, use the VM’s private IP (e.g., 10.x/192.168.x) and keep the firewall open only to that network.

## 8) Quick checks
- Bot: run `/status` in Discord and expect a response
- Backend: http://localhost:8081/docs (FastAPI Swagger UI)
- Frontend: http://localhost:5173 (Vite dev server)
- OAuth login works and dashboard loads

## 9) Testing
```bash
.venv/bin/python -m pytest tests/ web/backend/tests/ -v
```

Frontend unit tests:
```bash
cd web/frontend
npm test -- --run
```

## 10) Preflight (staging) dry-run
Use the consolidated staging dry-run script to verify config, readiness, and optionally load bot extensions without login.

```bash
# Backend and bot API checks
.venv/bin/python scripts/staging_dry_run.py --backend-url http://localhost:8081 --bot-url http://127.0.0.1:8082

# Include bot extension smoke load (no Discord login)
.venv/bin/python scripts/staging_dry_run.py --bot-smoke --bot-timeout 3
```

This script honors `CONFIG_PATH` for config overrides and surfaces `config_status` without re-parsing on each call.

## Notes
- If the venv is not activated, prefix commands with `.venv/bin/python`.
- Stop services before pulling updates or migrating the database.
- If frontend assets change, rebuild with `npm run build` (and rerun `npm run dev` or `npm run preview`).
