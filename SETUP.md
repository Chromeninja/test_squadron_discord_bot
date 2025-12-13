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

# Fix permissions so nginx (www-data) can serve frontend files
chmod 755 /home/chrome
chmod -R 755 /home/chrome/test_squadron_discord_bot/web/frontend/dist
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
FRONTEND_URL=http://YOUR_PUBLIC_IP

COOKIE_SECURE=false
COOKIE_SAMESITE=lax

# Optional: set a bot owner ID for global access
# BOT_OWNER_ID=your_discord_user_id
EOF

chmod 600 .env
```

Notes:
- Use at least 32 random bytes for SESSION_SECRET and INTERNAL_API_KEY (for example: `openssl rand -hex 32`).
- DISCORD_REDIRECT_URI must match the Discord Developer Portal entry (use the exact IP or domain you register).
- FRONTEND_URL must match VITE_API_BASE and is used for OAuth redirects after login.
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
    server_name YOUR_PUBLIC_IP_OR_DOMAIN 192.168.1.236;

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

Note: The `server_name` directive accepts multiple space-separated values (public IP, internal LAN IP, domain). Replace `192.168.1.236` with your actual internal IP if testing from LAN. Remove it for production.

Enable site and remove default:

```bash
# Remove default nginx site (takes priority otherwise)
sudo rm -f /etc/nginx/sites-enabled/default

# Enable our site
sudo ln -s /etc/nginx/sites-available/test_squadron /etc/nginx/sites-enabled/

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
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

Check that services are running and ports are accessible:

```bash
# Check service status
sudo systemctl status test_squadron_backend test_squadron_bot

# Check listening ports (backend on 8081, nginx on 80/443)
sudo netstat -tlnp | grep -E ':(80|443|8081)'

# Test backend health (internal only)
curl http://127.0.0.1:8081/api/health/liveness

# Test frontend access (external)
curl http://YOUR_PUBLIC_IP_OR_DOMAIN

# Check firewall rules
sudo ufw status
```

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
cd web/frontend && npm install && VITE_API_BASE=http://YOUR_PUBLIC_IP npm run build && cd ../..
sudo systemctl start test_squadron_backend test_squadron_bot
```

## 13. Troubleshooting

### nginx 500 Internal Server Error

Nginx cannot read files in your home directory:

```bash
# Check nginx error logs
sudo tail -20 /var/log/nginx/error.log

# Fix permissions
chmod 755 /home/chrome
chmod -R 755 /home/chrome/test_squadron_discord_bot/web/frontend/dist
sudo systemctl reload nginx
```

### nginx shows "Welcome to nginx!" instead of frontend

Default site is taking priority:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

### Cannot access public IP externally

1. **Router port forwarding**: Forward ports 80 and 443 to your server's internal IP
2. **ISP blocking port 80**: Use port 8080 instead (update nginx `listen` and Discord redirect URI)
3. **Windows Firewall** (Hyper-V): Allow inbound ports 80/443 on the host

Test from external device (not same network):
```bash
# Check if your public IP is correct
curl -s https://api.ipify.org

# Test from https://www.canyouseeme.org/ with your IP:80
```

### Backend health returns 404

Use the correct health endpoint:
```bash
curl http://127.0.0.1:8081/api/health/liveness
```

### OAuth redirects to localhost after login

1. **Missing FRONTEND_URL**: Add `FRONTEND_URL=http://YOUR_PUBLIC_IP` to `.env`
2. **Mismatch in Discord Portal**: Ensure Discord Developer Portal redirect URI matches your IP/domain
3. **Restart backend**: `sudo systemctl restart test_squadron_backend` after changing `.env`

Verify:
```bash
grep FRONTEND_URL .env
sudo journalctl -u test_squadron_backend -n 20 | grep -i redirect
```

### Services fail to start

Check logs for errors:
```bash
sudo journalctl -u test_squadron_backend -n 50 --no-pager
sudo journalctl -u test_squadron_bot -n 50 --no-pager
```

### Validate full setup

```bash
# Services running
sudo systemctl is-active test_squadron_backend test_squadron_bot

# Ports listening
sudo netstat -tlnp | grep -E ':(80|8081|8082)'

# Frontend working
curl -s http://localhost | head -5

# Backend health
curl http://127.0.0.1:8081/api/health/liveness

# Internal API (bot-to-web)
curl http://127.0.0.1:8082/health
```