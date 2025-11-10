"""
Dependency injection for FastAPI routes.

Provides access to configuration, database, and session management.
"""

import os
import sys
from pathlib import Path

import httpx
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
    
    # Close internal API client
    if _internal_api_client:
        await _internal_api_client.close()
    
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


def require_any(*roles: str):
    """
    Factory function for role-based access control dependency.
    
    Creates a dependency that checks if user has any of the specified roles.
    Server-side role validation against config.
    
    Args:
        *roles: Role names to check (e.g., "admin", "moderator")
        
    Returns:
        FastAPI dependency function
        
    Example:
        @app.get("/admin/stats", dependencies=[Depends(require_any("admin"))])
        async def admin_stats(): ...
    """
    async def check_roles(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        """Check if user has any of the required roles."""
        has_access = False
        
        for role in roles:
            if role == "admin" and current_user.is_admin:
                has_access = True
                break
            elif role == "moderator" and current_user.is_moderator:
                has_access = True
                break
        
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied - requires one of: {', '.join(roles)}",
            )
        
        return current_user
    
    return check_roles


# Internal API client for proxying requests to bot's internal server
class InternalAPIClient:
    """
    HTTP client for calling the bot's internal API.
    
    Handles authentication and provides typed methods for internal endpoints.
    """
    
    def __init__(self):
        self.base_url = os.getenv("INTERNAL_API_URL", "http://127.0.0.1:8082")
        self.api_key = os.getenv("INTERNAL_API_KEY", "")
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=10.0
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get_health_report(self):
        """Get comprehensive health report from internal API."""
        client = await self._get_client()
        response = await client.get("/health/report")
        response.raise_for_status()
        return response.json()
    
    async def get_last_errors(self, limit: int = 1):
        """Get most recent error log entries."""
        client = await self._get_client()
        response = await client.get("/errors/last", params={"limit": limit})
        response.raise_for_status()
        return response.json()
    
    async def export_logs(self, max_bytes: int = 1048576):
        """Export bot logs as downloadable content."""
        client = await self._get_client()
        response = await client.get("/logs/export", params={"max_bytes": max_bytes})
        response.raise_for_status()
        return response.content


# Global internal API client instance
_internal_api_client: InternalAPIClient | None = None


def get_internal_api_client() -> InternalAPIClient:
    """Get the global InternalAPIClient instance."""
    global _internal_api_client
    if _internal_api_client is None:
        _internal_api_client = InternalAPIClient()
    return _internal_api_client
