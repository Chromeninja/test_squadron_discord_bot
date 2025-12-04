# Web Admin Dashboard

A minimal, clean web admin interface for the Test Squadron Discord bot, built with FastAPI (backend) and React (frontend).

## Features

- **Discord OAuth2 Authentication**: Secure login with Discord
- **Role-Based Access Control**: Access controlled by Discord roles (Bot Admin, Discord Manager, Moderator, Staff)
- **Dashboard**: View verification stats and voice channel metrics
- **User Search**: Search and view verification records by user ID, RSI handle, or community moniker
- **Voice Channel Search**: Look up voice channels by user ID

## Architecture

### Backend (FastAPI)
- **Framework**: FastAPI with async support
- **Database**: Reuses existing SQLite database via `services/db/database.py`
- **Authentication**: Discord OAuth2 with JWT session tokens
- **Authorization**: Checks user IDs against `config/config.yaml` roles

### Frontend (React + Vite)
- **Framework**: React 18 with TypeScript
- **Styling**: TailwindCSS
- **Build**: Vite for fast development
- **API Client**: Axios with credential support

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Discord Developer Application (for OAuth2)

### Step 1: Discord OAuth2 Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application (or use existing bot application)
3. Navigate to **OAuth2** → **General**
4. Add redirect URL: `http://localhost:8081/auth/callback`
5. Copy your **Client ID** and **Client Secret**

### Step 2: Environment Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your Discord OAuth2 credentials:
   ```bash
   DISCORD_CLIENT_ID=your_client_id_here
   DISCORD_CLIENT_SECRET=your_client_secret_here
   DISCORD_REDIRECT_URI=http://localhost:8081/auth/callback
   SESSION_SECRET=change_me_to_random_string
   ```

### Step 3: Backend Setup

1. Navigate to backend directory:
   ```bash
   cd web/backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the backend:
   ```bash
   uvicorn app:app --reload --port 8081
   ```

   The API will be available at `http://localhost:8081`

### Step 4: Frontend Setup

1. Navigate to frontend directory (in a new terminal):
   ```bash
   cd web/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```

   The frontend will be available at `http://localhost:5173`

### Step 5: Access the Dashboard

1. Open your browser to `http://localhost:5173`
2. Click "Login with Discord"
3. Authorize the application
4. You'll be redirected to the dashboard (if you have moderator or higher role)

## VS Code Debugging

The project includes pre-configured launch configurations:

### Individual Debugging

- **Web Backend (FastAPI)**: Debug the FastAPI backend
- **Web Frontend (Vite Dev Server)**: Debug the React frontend

### Compound Debugging

- **🌐 Web Admin Only**: Runs both backend and frontend together
- **🚀 Full Stack**: Runs bot + backend + frontend together

To use:
1. Open VS Code
2. Go to Run and Debug panel (Ctrl+Shift+D)
3. Select desired configuration
4. Press F5 to start debugging

## Testing

### Backend Tests

Run backend tests with pytest:

```bash
cd web/backend
pytest tests/ -v
```

Tests use a temporary SQLite database and include:
- Authentication flow tests
- Stats endpoint tests
- User search tests
- Voice channel search tests

### Frontend Tests

Run frontend tests (basic smoke tests):

```bash
cd web/frontend
npm test
```

## Docker Compose (Optional)

For containerized development:

```bash
docker-compose up --build
```

This will start:
- Backend API on `http://localhost:8081`
- Frontend on `http://localhost:5173`

## API Endpoints

### Authentication
- `GET /auth/login` - Initiate Discord OAuth2 flow
- `GET /auth/callback` - OAuth2 callback handler
- `GET /api/auth/me` - Get current user session
- `POST /auth/logout` - Clear session

### Statistics
- `GET /api/stats/overview` - Dashboard statistics (requires auth)

### Users
- `GET /api/users/search?query=<term>&page=1&page_size=20` - Search verification records (requires auth)

### Voice
- `GET /api/voice/search?user_id=<id>` - Search voice channels by user (requires auth)

## Project Structure

```
web/
├── backend/
│   ├── app.py                 # FastAPI application
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile
│   ├── core/
│   │   ├── dependencies.py    # Dependency injection
│   │   ├── security.py        # Auth & session management
│   │   └── schemas.py         # Pydantic models
│   ├── routes/
│   │   ├── auth.py           # Authentication endpoints
│   │   ├── stats.py          # Statistics endpoints
│   │   ├── users.py          # User search endpoints
│   │   └── voice.py          # Voice channel endpoints
│   └── tests/
│       ├── conftest.py       # Test fixtures
│       ├── test_auth.py
│       ├── test_stats.py
│       ├── test_users.py
│       └── test_voice.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── Dockerfile
    ├── src/
    │   ├── App.tsx           # Main app component
    │   ├── main.tsx          # Entry point
    │   ├── api/
    │   │   ├── client.ts     # Axios configuration
    │   │   └── endpoints.ts  # API functions & types
    │   └── pages/
    │       ├── Dashboard.tsx # Stats overview
    │       ├── Users.tsx     # User search
    │       └── Voice.tsx     # Voice search
    └── index.html
```

## Security Notes

⚠️ **Local Development Only**: This setup is for local development and testing. For production:

1. Enable HTTPS and set `secure: true` on cookies
2. Use a strong, random `SESSION_SECRET`
3. Add CSRF protection for state-changing operations
4. Implement rate limiting
5. Add proper error logging and monitoring
6. Review and harden CORS settings

## Access Control

The dashboard checks user roles based on the hierarchical permission system in `config/config.yaml`:

```yaml
roles:
  bot_owner: 123456789012345678  # Bot owner user ID (full access)
  bot_admins: [123456789012345678, 987654321098765432]  # Bot Admin role IDs (full access)
  discord_managers: [111111111111111111]  # Discord Manager role IDs (full access)
  moderators: [222222222222222222]  # Moderator role IDs (full access)
  staff: [333333333333333333]  # Staff role IDs (read-only access)
```

Users with **Moderator** role or higher can access the full dashboard. **Staff** role users get read-only access to dashboards and statistics.

## Troubleshooting

### "Access Denied" after logging in

- Verify your Discord user ID has at least the **Staff** role in `config/config.yaml` (for read-only access) or **Moderator** role (for full access)
- User IDs must be strings in YAML (wrapped in quotes)

### Backend won't start

- Ensure you're in the `web/backend` directory
- Check that all environment variables are set in `.env`
- Verify database path is accessible

### Frontend can't reach backend

- Ensure backend is running on port 8081
- Check that CORS is properly configured in `app.py`
- Verify proxy settings in `vite.config.ts`

### OAuth redirect error

- Ensure `DISCORD_REDIRECT_URI` in `.env` matches the Discord Developer Portal setting exactly
- URL must be `http://localhost:8081/auth/callback` for local development

## Contributing

When making changes:

1. Backend changes: Update tests in `web/backend/tests/`
2. Frontend changes: Ensure TypeScript types are correct
3. API changes: Update both backend endpoints and frontend client
4. Run tests before committing

## License

Same as parent project.
