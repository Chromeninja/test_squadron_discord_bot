"""
Dependency injection for FastAPI routes.

Provides access to configuration, database, and session management.
"""

import sys
from pathlib import Path

from fastapi import Cookie, Depends, HTTPException

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.config_loader import ConfigLoader
from services.config_service import ConfigService
from services.db.database import Database

from .schemas import UserProfile
from .security import decode_session_token, SESSION_COOKIE_NAME

# Global service instances
_config_service: ConfigService | None = None
_config_loader: ConfigLoader | None = None


async def initialize_services():
    """Initialize services on application startup."""
    global _config_service, _config_loader

    # Load global config (use absolute path from project root)
    _config_loader = ConfigLoader()
    config_path = project_root / "config" / "config.yaml"
    config_dict = _config_loader.load_config(str(config_path))

    # Initialize database with configured path
    db_path = config_dict.get("database", {}).get("path", "TESTDatabase.db")
    # Make db_path absolute if relative
    if not Path(db_path).is_absolute():
        db_path = str(project_root / db_path)
    
    await Database.initialize(db_path)

    # Initialize config service
    _config_service = ConfigService()
    await _config_service.initialize()

    print(f"✓ Services initialized (DB: {db_path})")


async def shutdown_services():
    """Cleanup services on application shutdown."""
    if _config_service:
        await _config_service.shutdown()
    print("✓ Services shut down")


def get_config_service() -> ConfigService:
    """Get the global ConfigService instance."""
    if _config_service is None:
        raise RuntimeError("ConfigService not initialized")
    return _config_service


def get_config_loader() -> ConfigLoader:
    """Get the global ConfigLoader instance."""
    if _config_loader is None:
        raise RuntimeError("ConfigLoader not initialized")
    return _config_loader


async def get_db():
    """
    Dependency for database access.

    Yields a connection context manager from the Database class.
    """
    async with Database.get_connection() as conn:
        yield conn


async def get_current_user(
    session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> UserProfile:
    """
    Dependency to get the current authenticated user.

    Validates session cookie and returns user profile.
    Raises 401 if not authenticated.

    Args:
        session: Session token from cookie

    Returns:
        UserProfile of authenticated user

    Raises:
        HTTPException: 401 if not authenticated
    """
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = decode_session_token(session)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return UserProfile(**user_data)


async def require_admin_or_moderator(
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """
    Dependency to require admin or moderator role.

    Checks if user has admin or moderator permissions.
    Raises 403 if not authorized.

    Args:
        current_user: Authenticated user from get_current_user dependency

    Returns:
        UserProfile if authorized

    Raises:
        HTTPException: 403 if not admin or moderator
    """
    if not (current_user.is_admin or current_user.is_moderator):
        raise HTTPException(
            status_code=403,
            detail="Access denied - admin or moderator role required",
        )
    return current_user
