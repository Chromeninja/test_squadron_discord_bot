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
sudo chmod 755 /home/chrome
sudo chmod -R 755 /home/chrome/test_squadron_discord_bot/web/frontend/dist
```

## 5. Environment File

Find your public IP (if you do not have a domain yet):

```bash
curl -4 ifconfig.me
```

Create .env in the project root. Replace `YOUR_PUBLIC_IP` with your actual IP or domain.

```bash
nano .env
# paste the contents below, then save/exit

# === Required Secrets ===
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret

# === Deployment ===
# All OAuth redirect URIs are derived from PUBLIC_URL:
#   - /auth/callback     (user login)
#   - /auth/bot-callback (bot invite)
PUBLIC_URL=http://YOUR_PUBLIC_IP

# Generate secrets with: openssl rand -hex 32
SESSION_SECRET=generate_with_openssl
INTERNAL_API_KEY=generate_with_openssl

# === Optional ===
# ENV=production
# BOT_OWNER_IDS=123456789,987654321
# INTERNAL_API_HOST=127.0.0.1
# INTERNAL_API_PORT=8082
```

## 6. Configuration

- Primary config: config/config.yaml
- Reference template: config/config-example.yaml

Copy and adjust as needed:

```bash
cp config/config-example.yaml config/config.yaml
# edit config/config.yaml
```

### Important Notes

- `PUBLIC_URL` is the single source of truth. It replaces legacy variables (`DISCORD_REDIRECT_URI`, `DISCORD_BOT_REDIRECT_URI`, `FRONTEND_URL`, `VITE_API_BASE`); these are derived automatically.
- In the Discord Developer Portal, register both redirect URIs: `PUBLIC_URL/auth/callback` and `PUBLIC_URL/auth/bot-callback`.
- `COOKIE_SECURE` auto-detects from `PUBLIC_URL` scheme (`https` => true). Override only if necessary via `.env`.

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

Create nginx site config (replace `YOUR_PUBLIC_IP_OR_DOMAIN` with your public IP or domain, and add your LAN IP if you want local testing):

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
        
        # Increase buffer size for large session cookies
        proxy_buffer_size 16k;
        proxy_buffers 4 16k;
        proxy_busy_buffers_size 32k;
    }

    location /auth {
        proxy_pass http://127.0.0.1:8081;
        include proxy_params;
        
        # Increase buffer size for large session cookies
        proxy_buffer_size 16k;
        proxy_buffers 4 16k;
        proxy_busy_buffers_size 32k;
    }
}
EOF
```

Note: The `server_name` directive accepts multiple space-separated values (public IP, internal LAN IP, domain). Add your LAN IP if testing from inside your network (for example `server_name YOUR_PUBLIC_IP_OR_DOMAIN 192.168.1.236;`).

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
sudo ss -tlnp | grep -E ':(80|443|8081)'

# Test backend health (internal only)

# Check firewall rules
sudo ufw status
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

```

- Backend health: `curl https://your-domain.com/api/health`
- Discord bot: run `/status` in a server where the bot is installed
- OAuth: open https://your-domain.com, log in with Discord, and confirm dashboard loads
- Logs: `journalctl -u test_squadron_backend -f` and `journalctl -u test_squadron_bot -f`
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

1. **PUBLIC_URL mismatch**: Ensure `PUBLIC_URL` in `.env` matches your external URL. `FRONTEND_URL` is derived automatically; avoid setting it manually unless overriding a dev setup.
2. **Discord Portal redirects**: Register both redirect URIs using `PUBLIC_URL`: `/auth/callback` and `/auth/bot-callback`.
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