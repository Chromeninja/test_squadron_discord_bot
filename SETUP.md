# TEST Squadron Discord Bot — Production Deployment (Linux)

This guide deploys the Discord bot, FastAPI backend, and Vite frontend on a single Linux server using systemd and nginx.

For local development, see VS_CODE_SETUP.md.

## Requirements

- Debian 11+ or Ubuntu 22.04+
- Minimum 2 GB RAM
- Python 3.12+
- Node.js 20+
- Discord Bot token
- Discord OAuth application (client ID, secret, redirect URI)
- Domain name (recommended for HTTPS)

<<<<<<< HEAD
## 1) Clone repo
```bash
git clone https://github.com/Chromeninja/test_squadron_discord_bot.git test_discord_bot
cd test_discord_bot
```
=======
## 1. System Packages

Update the system and install required packages:

sudo apt update
sudo apt install -y git curl nginx python3 python3-venv python3-pip

Install Node.js 20:

curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

## 2. Clone Repository & Python Setup

git clone https://github.com/Chromeninja/test_squadron_discord_bot.git
cd test_squadron_discord_bot
>>>>>>> 7635956 (feat: update setup documentation for production deployment and systemd services; refactor verification message ID handling to use database)

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -r web/backend/requirements.txt

## 3. Build Frontend

cd web/frontend
npm install
npm run build
cd ../..

## 4. Environment Configuration

Create a .env file in the project root:

DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=https://your-domain.com/auth/callback

DB_PATH=./test_squadron.db
SESSION_SECRET=generate_with_openssl
INTERNAL_API_KEY=generate_with_openssl

VITE_API_BASE=https://your-domain.com
ENVIRONMENT=production
LOG_LEVEL=INFO

COOKIE_SECURE=true
COOKIE_SAMESITE=lax

Secure the file:

chmod 600 .env

Notes:
- SESSION_SECRET and INTERNAL_API_KEY should be at least 32 random bytes
- .env must never be committed to version control
- DISCORD_REDIRECT_URI must exactly match the value configured in the Discord Developer Portal

## 5. Application Config

Primary configuration:
- config/config.yaml

Reference template:
- config/config-example.yaml

## 6. systemd Services

### Backend (FastAPI)

<<<<<<< HEAD
> Run the **backend + bot as services**, and serve the **frontend as static files**.
=======
Create /etc/systemd/system/test_squadron_backend.service:
>>>>>>> 7635956 (feat: update setup documentation for production deployment and systemd services; refactor verification message ID handling to use database)

[Unit]
After=network.target

[Service]
User=chrome
WorkingDirectory=/home/chrome/test_squadron_discord_bot
EnvironmentFile=/home/chrome/test_squadron_discord_bot/.env
ExecStart=/home/chrome/test_squadron_discord_bot/.venv/bin/python -m uvicorn app:app --app-dir web/backend --host 0.0.0.0 --port 8081
Restart=on-failure

[Install]
WantedBy=multi-user.target

### Discord Bot

Create /etc/systemd/system/test_squadron_bot.service:

[Unit]
After=network.target

[Service]
User=chrome
WorkingDirectory=/home/chrome/test_squadron_discord_bot
EnvironmentFile=/home/chrome/test_squadron_discord_bot/.env
ExecStart=/home/chrome/test_squadron_discord_bot/.venv/bin/python bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target

Enable and start services:

sudo systemctl daemon-reload
sudo systemctl enable --now test_squadron_backend test_squadron_bot

## 7. nginx Configuration

Create /etc/nginx/sites-available/test_squadron:

server {
    listen 80;
    server_name your-domain.com;

    root /home/chrome/test_squadron_discord_bot/web/frontend/dist;
    index index.html;

    location / {
        try_files $uri /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8081;
        include proxy_params;
    }

    location /auth {
        proxy_pass http://127.0.0.1:8081;
        include proxy_params;
    }
}

Enable the site:

sudo ln -s /etc/nginx/sites-available/test_squadron /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

## 8. HTTPS (Recommended)

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

## 9. Firewall

sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable

Do not expose backend ports (8081) directly.

## 10. Verification

Backend health check:
curl https://your-domain.com/api/health

Discord:
- Run /status in a server where the bot is installed

OAuth:
- Load https://your-domain.com
- Complete Discord login
- Verify dashboard loads

Logs:
journalctl -u test_squadron_backend -f
journalctl -u test_squadron_bot -f

## 11. Updating the Deployment

- sudo systemctl stop test_squadron_backend test_squadron_bot
- git pull
- source .venv/bin/activate
- pip install -r requirements.txt -r web/backend/requirements.txt
- cd web/frontend && npm install && npm run build && cd ../..
- sudo systemctl start test_squadron_backend test_squadron_bot