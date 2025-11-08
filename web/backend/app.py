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
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load environment variables from project root .env file
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / ".env")

from core.dependencies import get_db, initialize_services, shutdown_services
from routes import auth, stats, users, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup services on app startup/shutdown."""
    await initialize_services()
    yield
    await shutdown_services()


app = FastAPI(
    title="Test Squadron Admin Dashboard",
    description="Web admin interface for Discord bot management",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration - permissive for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.api_router, prefix="/api/auth", tags=["auth"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "test-squadron-admin-api"}


@app.exception_handler(401)
async def unauthorized_handler(request, exc):
    """Return standardized 401 response."""
    return JSONResponse(
        status_code=401,
        content={
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required",
            },
        },
    )


@app.exception_handler(403)
async def forbidden_handler(request, exc):
    """Return standardized 403 response."""
    return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "error": {
                "code": "FORBIDDEN",
                "message": "Access denied - admin or moderator role required",
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
