# Web Dashboard Quick Start Guide

## What Was Built

A minimal, production-ready web admin dashboard for the Test Squadron Discord Bot with:

✅ **Backend (FastAPI)**
- Discord OAuth2 authentication
- Role-based access control (checks `config/config.yaml`)
- REST API endpoints for stats, user search, and voice channels
- Reuses existing database and services
- Comprehensive test suite with temp DB

✅ **Frontend (React + Vite + TypeScript)**
- Clean, dark-themed UI with TailwindCSS
- Three main views: Dashboard, Users, Voice
- Responsive design with keyboard accessibility
- Type-safe API client with Axios

✅ **Development Tools**
- VS Code debugging configurations
- Docker Compose for containerized development
- pytest test suite for backend
- Environment configuration examples

## File Structure Created

```
web/
├── README.md                    # Comprehensive documentation
├── backend/
│   ├── app.py                  # FastAPI application entry point
│   ├── requirements.txt        # Python dependencies
│   ├── Dockerfile
│   ├── core/
│   │   ├── dependencies.py     # DI: ConfigService, DB, auth
│   │   ├── security.py         # OAuth2, JWT, session handling
│   │   └── schemas.py          # Pydantic request/response models
│   ├── routes/
│   │   ├── auth.py            # /auth/login, /auth/callback, /api/auth/me
│   │   ├── stats.py           # /api/stats/overview
│   │   ├── users.py           # /api/users/search
│   │   └── voice.py           # /api/voice/search
│   └── tests/
│       ├── conftest.py        # Test fixtures with temp DB
│       ├── test_auth.py
│       ├── test_stats.py
│       ├── test_users.py
│       └── test_voice.py
└── frontend/
    ├── package.json
    ├── vite.config.ts         # Dev server with proxy to backend
    ├── Dockerfile
    ├── src/
    │   ├── App.tsx            # Main app with auth guard
    │   ├── main.tsx
    │   ├── index.css          # Tailwind imports
    │   ├── api/
    │   │   ├── client.ts      # Axios with credentials
    │   │   └── endpoints.ts   # Typed API functions
    │   └── pages/
    │       ├── Dashboard.tsx  # Stats cards
    │       ├── Users.tsx      # User search table
    │       └── Voice.tsx      # Voice channel search
    └── index.html

.vscode/
├── launch.json                # Updated with FastAPI + Vite configs
└── (tasks.json exists)

.env.example                   # Added web dashboard env vars
docker-compose.yml             # Backend + Frontend + DB services
```

## How to Run Locally

### Prerequisites

1. **Python 3.11+** installed
2. **Node.js 20+** installed
3. **Discord Developer Application** set up

### Step 1: Discord OAuth2 Setup

1. Go to https://discord.com/developers/applications
2. Select your application (or create new)
3. Go to **OAuth2** → **General**
4. Add redirect URL: `http://localhost:8081/auth/callback`
5. Copy **Client ID** and **Client Secret**

### Step 2: Configure Environment

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Discord credentials:
   ```bash
   DISCORD_CLIENT_ID=your_client_id_here
   DISCORD_CLIENT_SECRET=your_client_secret_here
   DISCORD_REDIRECT_URI=http://localhost:8081/auth/callback
   SESSION_SECRET=change_to_random_string_in_production
   ```

### Step 3: Run Backend

```bash
cd web/backend

# Create virtual environment (first time only)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn app:app --reload --port 8081
```

Backend will be available at http://localhost:8081

### Step 4: Run Frontend (New Terminal)

```bash
cd web/frontend

# Install dependencies (first time only)
npm install

# Start dev server
npm run dev
```

Frontend will be available at http://localhost:5173

### Step 5: Access Dashboard

1. Open browser to http://localhost:5173
2. Click "Login with Discord"
3. Authorize the application
4. Access granted if you're in `config/config.yaml` roles

## Using VS Code Debugging

1. Open VS Code
2. Press `Ctrl+Shift+D` (Run and Debug)
3. Select configuration:
   - **Web Backend (FastAPI)** - Debug backend only
   - **Web Frontend (Vite Dev Server)** - Debug frontend only
   - **🌐 Web Admin Only** - Run both together
   - **🚀 Full Stack** - Run bot + backend + frontend
4. Press `F5` to start

## Running Tests

### Backend Tests

```bash
cd web/backend
pytest tests/ -v
```

Tests use a temporary SQLite database and cover:
- ✅ Auth endpoints (login redirect, session validation)
- ✅ Stats endpoint (counts by status, active channels)
- ✅ User search (by ID, handle, moniker, pagination)
- ✅ Voice search (by user ID)
- ✅ Authorization checks (admin/mod vs unauthorized)

## API Endpoints

### Authentication
- `GET /auth/login` - Redirect to Discord OAuth
- `GET /auth/callback` - Handle OAuth callback
- `GET /api/auth/me` - Get current user session
- `POST /auth/logout` - Clear session

### Protected Endpoints (Require Admin/Mod Role)
- `GET /api/stats/overview` - Dashboard statistics
- `GET /api/users/search?query=<term>&page=1&page_size=20` - Search verification records
- `GET /api/voice/search?user_id=<id>` - Search voice channels

## Access Control

Users must have appropriate roles configured in `config/config.yaml` using the hierarchical role system:

```yaml
roles:
  bot_owner: 123456789012345678  # Bot owner user ID (full access)
  bot_admins: [246604397155581954, 987654321098765432]  # Bot Admin role IDs (full access)
  discord_managers: [111111111111111111]  # Discord Manager role IDs (full access)
  moderators: [222222222222222222]  # Moderator role IDs (full access)
  staff: [333333333333333333]  # Staff role IDs (read-only access)
  # Legacy support for backward compatibility:
  lead_moderators: [1428084144860303511]  # Fallback to moderators if not set
```

The dashboard enforces role-based access control on every request:
- **Moderator+**: Full administrative access
- **Staff**: Read-only dashboard access

## Key Implementation Details

### Backend
- **Database**: Reuses existing `services/db/database.py` async SQLite wrapper
- **Config**: Uses existing `config/config_loader.py` and `services/config_service.py`
- **Sessions**: JWT tokens in HttpOnly cookies (signed with SESSION_SECRET)
- **OAuth Flow**: Exchange code → fetch user → check roles → create session
- **Error Handling**: Standardized JSON responses with success/error structure

### Frontend
- **State Management**: React hooks (useState, useEffect)
- **API Client**: Axios with `withCredentials: true` for cookie support
- **Auth Guard**: Checks `/api/auth/me` on app load
- **Styling**: TailwindCSS with dark slate theme
- **Type Safety**: Full TypeScript with typed API responses

## Docker Compose (Optional)

For containerized development:

```bash
docker-compose up --build
```

Access:
- Backend: http://localhost:8081
- Frontend: http://localhost:5173

## Troubleshooting

### "Access Denied" after login
- ✅ Check your Discord user ID is in `config/config.yaml`
- ✅ Ensure IDs are strings (wrapped in quotes in YAML)
- ✅ Restart backend after config changes

### Backend won't start
- ✅ Check `.env` has all required variables
- ✅ Ensure database file is accessible
- ✅ Verify Python dependencies installed

### Frontend can't reach backend
- ✅ Ensure backend running on port 8081
- ✅ Check browser console for CORS errors
- ✅ Verify proxy config in `vite.config.ts`

### OAuth redirect error
- ✅ Redirect URI in `.env` must match Discord Developer Portal exactly
- ✅ Use `http://localhost:8081/auth/callback` for local dev

## Security Notes

⚠️ **This is configured for local development only!**

For production deployment:
1. ✅ Enable HTTPS and set `secure: true` on cookies
2. ✅ Use strong random `SESSION_SECRET`
3. ✅ Add CSRF protection for state-changing operations
4. ✅ Implement rate limiting on auth endpoints
5. ✅ Review and restrict CORS origins
6. ✅ Add proper logging and monitoring
7. ✅ Use environment-specific configs

## Next Steps

1. **Test the flow**: Login → View dashboard → Search users → Search voice channels
2. **Run backend tests**: `cd web/backend && pytest tests/ -v`
3. **Customize**: Adjust colors/styling in frontend components
4. **Extend**: Add more endpoints or dashboard features as needed
5. **Read full docs**: See `web/README.md` for complete documentation

## Getting Help

- **Full Documentation**: `web/README.md`
- **Bot Setup**: `SETUP.txt` in project root
- **Code Structure**: Inline comments in all major files
- **Tests**: Check `web/backend/tests/` for examples

---

**Built with**: FastAPI, React, TypeScript, TailwindCSS, Vite, pytest, Docker
**For**: Test Squadron Discord Bot local development and testing
