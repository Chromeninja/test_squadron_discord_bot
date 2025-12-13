# TEST Squadron Discord Bot — Production Deployment (Linux)

Deploy the Discord bot, FastAPI backend, and Vite frontend on a single Debian-based server using systemd and nginx. These steps assume a clean Debian 12+ VM with sudo access. For local development, see VS_CODE_SETUP.md.

## Requirements

- Debian 12+ (or Ubuntu 22.04+)
- 2 GB RAM minimum
- Discord Bot token
- Discord OAuth app (client ID, secret, redirect URI)
- Domain name for HTTPS (recommended)

## 1. System Prep (root or sudo)

```bash
sudo apt update
sudo apt install -y git curl nginx ufw python3 python3-venv python3-pip

# Node.js 20 (NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Optional: verify versions
python3 --version
node --version
git --version
```

## 2. Clone Repository

```bash
git clone https://github.com/Chromeninja/test_squadron_discord_bot.git
cd test_squadron_discord_bot
```

## 3. Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -r web/backend/requirements.txt
```

## 4. Frontend Build

```bash
cd web/frontend
npm install
VITE_API_BASE=http://YOUR_PUBLIC_IP npm run build
cd ../..
```

## 5. Environment File

Find your public IP (if you do not have a domain yet):

```bash
curl -4 ifconfig.me
```

Create .env in the project root (use nano or the heredoc below). Replace `YOUR_PUBLIC_IP` if you are using an IP instead of a domain.

```bash
nano .env
# paste the contents below, then save/exit

# or use heredoc:
cat <<'EOF' > .env
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://YOUR_PUBLIC_IP/auth/callback

SESSION_SECRET=generate_with_openssl
INTERNAL_API_KEY=generate_with_openssl
INTERNAL_API_URL=http://127.0.0.1:8082

VITE_API_BASE=http://YOUR_PUBLIC_IP

COOKIE_SECURE=false
COOKIE_SAMESITE=lax

# Optional: set if serving frontend from a separate host (CORS allowlist)
# FRONTEND_URL=https://your-domain.com

# Optional: set a bot owner ID for global access
# BOT_OWNER_ID=your_discord_user_id
EOF

chmod 600 .env
```

Notes:
- Use at least 32 random bytes for SESSION_SECRET and INTERNAL_API_KEY (for example: `openssl rand -hex 32`).
- DISCORD_REDIRECT_URI must match the Discord Developer Portal entry (use the exact IP or domain you register).
- Set COOKIE_SECURE=true only after you add HTTPS.
- INTERNAL_API_URL only needs changing if you move the internal API off 127.0.0.1:8082.
- Keep .env out of version control.

## 6. Application Config

- Primary config: config/config.yaml
- Reference template: config/config-example.yaml

Copy and adjust as needed:

```bash
cp config/config-example.yaml config/config.yaml
# edit config/config.yaml
```

## 7. systemd Services

Replace `/home/chrome` and `chrome` below with your actual deploy user and path.

Create backend service:

```bash
sudo tee /etc/systemd/system/test_squadron_backend.service > /dev/null <<'EOF'
[Unit]
After=network.target

[Service]
User=chrome
WorkingDirectory=/home/chrome/test_squadron_discord_bot
EnvironmentFile=/home/chrome/test_squadron_discord_bot/.env
ExecStart=/home/chrome/test_squadron_discord_bot/.venv/bin/python -m uvicorn app:app --app-dir web/backend --host 0.0.0.0 --port 8081
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

Create bot service:

```bash
sudo tee /etc/systemd/system/test_squadron_bot.service > /dev/null <<'EOF'
[Unit]
After=network.target

[Service]
User=chrome
WorkingDirectory=/home/chrome/test_squadron_discord_bot
EnvironmentFile=/home/chrome/test_squadron_discord_bot/.env
ExecStart=/home/chrome/test_squadron_discord_bot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start both services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now test_squadron_backend test_squadron_bot
sudo systemctl status test_squadron_backend test_squadron_bot
```

## 8. nginx

Create nginx site config (replace `your-domain.com` with your public IP or domain):

```bash
sudo tee /etc/nginx/sites-available/test_squadron > /dev/null <<'EOF'
server {
    listen 80;
    server_name YOUR_PUBLIC_IP_OR_DOMAIN;

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
EOF
```

Enable and restart nginx:

```bash
sudo ln -s /etc/nginx/sites-available/test_squadron /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 9. HTTPS (recommended)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 10. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```

Do not expose port 8081 publicly.

## 11. Verification

- Backend health: `curl https://your-domain.com/api/health`
- Discord bot: run `/status` in a server where the bot is installed
- OAuth: open https://your-domain.com, log in with Discord, and confirm dashboard loads
- Logs: `journalctl -u test_squadron_backend -f` and `journalctl -u test_squadron_bot -f`

## 12. Updating

```bash
sudo systemctl stop test_squadron_backend test_squadron_bot
cd /home/chrome/test_squadron_discord_bot
git pull
source .venv/bin/activate
pip install -r requirements.txt -r web/backend/requirements.txt
cd web/frontend && npm install && npm run build && cd ../..
sudo systemctl start test_squadron_backend test_squadron_bot
```