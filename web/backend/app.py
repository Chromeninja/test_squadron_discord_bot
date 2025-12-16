"""
FastAPI Web Dashboard for Test Squadron Discord Bot

A minimal admin dashboard providing:
- Discord OAuth2 authentication
- Stats overview (verification, voice channels)
- User search (verification records)
- Voice channel search

For local development/testing only.
"""

import os
import sys
from contextlib import asynccontextmanager

# Import centralized project_root from dependencies
from core.dependencies import project_root
from core.security import clear_session_cookie
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Use centralized project root
_PROJECT_ROOT = project_root()
sys.path.insert(0, str(_PROJECT_ROOT))

# Import bot's structured logging setup
from utils.logging import get_logger, setup_logging

# Setup structured logging for backend (same as bot)
# Use absolute path to avoid duplicated nested directories when CWD is web/backend
_LOG_PATH = _PROJECT_ROOT / "web" / "backend" / "logs" / "bot.log"
setup_logging(log_file=str(_LOG_PATH))
logger = get_logger(__name__)

# Load environment variables from project root .env file
env_path = _PROJECT_ROOT / ".env"
logger.info("Loading backend environment", extra={"env_path": str(env_path)})
load_dotenv(env_path)

# Debug: Check if INTERNAL_API_KEY was loaded
api_key = os.getenv("INTERNAL_API_KEY")
if api_key:
    logger.info(
        "INTERNAL_API_KEY loaded successfully", extra={"key_length": len(api_key)}
    )
else:
    logger.warning("INTERNAL_API_KEY not found in environment")

from core.dependencies import initialize_services, shutdown_services
from core.request_id import RequestIDMiddleware
from routes import (
    admin_users,
    auth,
    errors,
    guilds,
    health,
    logs,
    stats,
    users,
    voice,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup services on app startup/shutdown."""
    # Security validation: Ensure SESSION_SECRET is properly configured in production
    env = os.getenv("ENV", "development").lower()
    session_secret = os.getenv("SESSION_SECRET", "")
    default_secret = "dev_only_change_me_in_production"

    if env == "production" and (not session_secret or session_secret == default_secret):
        logger.critical(
            "SECURITY: SESSION_SECRET must be set to a secure value in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        raise RuntimeError(
            "SESSION_SECRET not configured for production. "
            "Set a secure random value in your environment."
        )

    if session_secret == default_secret:
        logger.warning(
            "SESSION_SECRET is using default development value. "
            "Set a secure value before deploying to production."
        )

    await initialize_services()
    yield
    await shutdown_services()


app = FastAPI(
    title="Test Squadron Admin Dashboard",
    description="Web admin interface for Discord bot management",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration - include prod FRONTEND_URL when provided
cors_origins = ["http://localhost:5173", "http://localhost:3000"]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    cors_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request ID middleware for correlation tracking
app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.api_router, prefix="/api/auth", tags=["auth"])
app.include_router(guilds.router)
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(admin_users.router, prefix="/api/admin", tags=["admin"])
app.include_router(health.router)
app.include_router(errors.router)
app.include_router(logs.router)


# Serve built frontend assets in production
frontend_dist = _PROJECT_ROOT / "web" / "frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dist), html=True),
        name="static",
    )


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "test-squadron-admin-api"}


@app.exception_handler(401)
async def unauthorized_handler(request, exc):
    """Return standardized 401 response and clear session if role was revoked."""
    # Default payload
    code = "UNAUTHORIZED"
    message = "Authentication required"

    # If detail contains structured payload, prefer it
    try:
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            err_code = detail.get("code")
            err_msg = detail.get("message")
            if err_code:
                code = err_code
            if err_msg:
                message = err_msg
    except Exception:
        pass

    response = JSONResponse(
        status_code=401,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )

    # If the error indicates role revocation, clear session cookie
    if code == "role_revoked":
        clear_session_cookie(response)

    return response


@app.exception_handler(403)
async def forbidden_handler(request, exc):
    """Return standardized 403 response."""
    # Extract detail from HTTPException if available
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        message = detail.get("message", "Access denied")
    elif isinstance(detail, str):
        message = detail
    else:
        message = "Access denied"

    return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "error": {
                "code": "FORBIDDEN",
                "message": message,
            },
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Return standardized 500 response."""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            },
        },
    )
