"""
Test configuration and fixtures for backend tests.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
import sys

sys.path.insert(0, str(project_root))

# Add backend directory to path so we can import app
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

import contextlib

from core import dependencies

from config.config_loader import ConfigLoader
from services.config_service import ConfigService
from services.db.database import Database


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def temp_db():
    """Create a temporary database for testing."""
    # Create temp file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Reset database initialization state for clean test
    Database._initialized = False

    # Initialize database - this calls init_schema which creates tables
    await Database.initialize(db_path)

    # Seed some test data
    async with Database.get_connection() as db:
        # Add test guild_settings for role configuration
        # Guild 123 with bot_admin and moderator roles
        await db.execute(
            """
            INSERT INTO guild_settings (guild_id, key, value)
            VALUES
                (123, 'roles.bot_admins', '[\"999111222\"]'),
                (123, 'roles.moderators', '[\"999111223\"]'),
                (123, 'roles.staff', '[\"999111224\"]'),
                (1, 'roles.bot_admins', '[\"999111222\"]'),
                (1, 'roles.moderators', '[\"999111223\"]'),
                (1, 'roles.staff', '[\"999111224\"]'),
                (2, 'roles.bot_admins', '[\"999111222\"]'),
                (2, 'roles.moderators', '[\"999111223\"]'),
                (2, 'roles.staff', '[\"999111224\"]'),
                (999, 'roles.bot_admins', '[\"999111222\"]'),
                (999, 'roles.moderators', '[\"999111223\"]'),
                (999, 'roles.staff', '[\"999111224\"]')
            """
        )

        # Add test verification records
        await db.execute(
            """
            INSERT INTO verification
            (user_id, rsi_handle, last_updated,
             community_moniker, main_orgs, affiliate_orgs)
            VALUES
                (123456789, 'TestUser1', 1234567890,
                 'Test Main', '["TEST"]', '[]'),
                (987654321, 'TestUser2', 1234567891,
                 'Test Affiliate', '[]', '["TEST"]'),
                (111222333, 'TestUser3', 1234567892,
                 NULL, '[]', '[]'),
                (444555666, 'TestUser4', 1234567893,
                 NULL, NULL, NULL)
            """
        )

        # Add test voice channel records
        await db.execute(
            """
            INSERT INTO voice_channels
            (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
            VALUES
                (1111, 2222, 123456789, 3333, 1234567890, 1234567900, 1),
                (1111, 2222, 123456789, 4444, 1234567891, 1234567901, 0),
                (1111, 2222, 987654321, 5555, 1234567892, 1234567902, 1)
            """
        )

        await db.commit()

    yield db_path

    # Cleanup
    with contextlib.suppress(Exception):
        os.unlink(db_path)


@pytest_asyncio.fixture
async def client(temp_db):
    """Create a test client for the FastAPI app."""
    # Seed backend dependencies because ASGITransport doesn't trigger lifespan in tests
    config_loader = ConfigLoader()
    dependencies._config_loader = config_loader

    config_service = ConfigService()
    await config_service.initialize()
    dependencies._config_service = config_service

    # Reset voice service singleton for fresh test state
    dependencies._voice_service = None

    # Import app after database and services are initialized
    from app import app

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_admin_session():
    """Create a mock session token for an admin user."""
    from core.security import create_session_token

    return create_session_token(
        {
            "user_id": "246604397155581954",  # Admin from config
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "123",  # Default test guild
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
                "1": {
                    "guild_id": "1",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
                "2": {
                    "guild_id": "2",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
            },
        }
    )


@pytest.fixture
def mock_moderator_session():
    """Create a mock session token for a moderator user."""
    from core.security import create_session_token

    return create_session_token(
        {
            "user_id": "1428084144860303511",  # Moderator from config
            "username": "TestModerator",
            "discriminator": "0002",
            "avatar": None,
            "active_guild_id": "123",  # Default test guild
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "moderator",
                    "source": "moderator_role",
                },
            },
        }
    )


@pytest.fixture
def mock_unauthorized_session():
    """Create a mock session token for an unauthorized user."""
    from core.security import create_session_token

    return create_session_token(
        {
            "user_id": "999999999",
            "username": "UnauthorizedUser",
            "discriminator": "0003",
            "avatar": None,
            "authorized_guilds": {},  # No guild permissions
        }
    )


class FakeInternalAPIClient:
    """Simple fake internal API client for tests."""

    def __init__(self):
        self.guilds: list[dict] = []
        self.roles_by_guild: dict[int, list[dict]] = {}
        self.guild_stats: dict[int, dict] = {}
        self.members_by_guild: dict[int, list[dict]] = {}
        self.member_data: dict[
            tuple[int, int], dict
        ] = {}  # (guild_id, user_id) -> member_data
        self.refresh_calls: list[dict] = []
        self.channels_by_guild: dict[int, list[dict]] = {}
        self.health_data: dict | None = None
        self.error_logs: list[dict] = []
        self.log_content: bytes = b"Mock log content\n"
        # Allow overriding method responses for specific tests
        self._health_report_override = None
        self._last_errors_override = None
        self._export_logs_override = None

    async def get_guilds(self) -> list[dict]:
        return self.guilds

    async def get_guild_roles(self, guild_id: int) -> list[dict]:
        return self.roles_by_guild.get(guild_id, [])

    async def get_guild_stats(self, guild_id: int) -> dict:
        """Return guild stats or default values."""
        return self.guild_stats.get(
            guild_id,
            {
                "guild_id": guild_id,
                "member_count": 100,  # Default test value
                "approximate_member_count": None,
            },
        )

    async def get_guild_members(
        self, guild_id: int, page: int = 1, page_size: int = 100
    ) -> dict:
        """Return paginated guild members."""
        members = self.members_by_guild.get(guild_id, [])
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_members = members[start_idx:end_idx]

        return {
            "members": page_members,
            "page": page,
            "page_size": page_size,
            "total": len(members),
        }

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict:
        """Return single guild member data."""
        key = (guild_id, user_id)
        if key in self.member_data:
            member = self.member_data[key].copy()  # Don't modify the original
            # Ensure role_ids is present for validation to work
            if "role_ids" not in member and "roles" in member:
                member["role_ids"] = [r.get("id") for r in member["roles"]]
            # Add source if missing
            if "source" not in member:
                member["source"] = "discord"

            # For role validation to pass, we need to ensure the user has one of the
            # configured role IDs (999111222 for bot_admin, 999111223 for moderator, 999111224 for staff)
            # Add the appropriate validation role ID based on user_id
            if user_id == 1428084144860303511:
                # Moderator user - ensure moderator role ID is present
                if "role_ids" not in member or "999111223" not in member.get(
                    "role_ids", []
                ):
                    if "role_ids" not in member:
                        member["role_ids"] = []
                    member["role_ids"].append("999111223")
            # All other users - ensure bot_admin role ID is present
            elif "role_ids" not in member or "999111222" not in str(
                member.get("role_ids", [])
            ):
                if "role_ids" not in member:
                    member["role_ids"] = []
                member["role_ids"].append("999111222")

            return member

        # Default member data - include test admin/moderator roles
        # Admin user: 246604397155581954 - gets bot_admin role ID 999111222
        # Moderator user: 1428084144860303511 - gets moderator role ID 999111223
        # Any other user: gets bot_admin role by default (for tests that use custom user IDs)
        roles = []
        if user_id == 1428084144860303511:
            # Moderator user gets moderator role
            roles = [{"id": "999111223", "name": "Moderator"}]
        else:
            # All other users get bot_admin role (including 246604397155581954 and test-specific IDs)
            roles = [{"id": "999111222", "name": "Bot Admin"}]

        return {
            "user_id": user_id,
            "username": f"User{user_id}",
            "discriminator": "0001",
            "global_name": f"User {user_id}",
            "avatar_url": None,
            "joined_at": "2024-01-01T00:00:00",
            "created_at": "2023-01-01T00:00:00",
            "roles": roles,
            "role_ids": [r["id"] for r in roles],
            "source": "discord",
        }

    async def notify_guild_settings_refresh(
        self, guild_id: int, source: str | None = None
    ) -> dict:
        self.refresh_calls.append({"guild_id": guild_id, "source": source})
        return {"status": "ok"}

    async def get_health_report(self) -> dict:
        """Return health report for testing."""
        if self._health_report_override is not None:
            if isinstance(self._health_report_override, Exception):
                raise self._health_report_override
            return self._health_report_override
        if self.health_data:
            return self.health_data
        return {
            "status": "healthy",
            "uptime_seconds": 3600,
            "db_ok": True,
            "discord_latency_ms": 45.0,
            "system": {
                "cpu_percent": 15.0,
                "memory_percent": 40.0,
            },
        }

    async def get_last_errors(self, limit: int = 1) -> dict:
        """Return recent error logs."""
        if self._last_errors_override is not None:
            if isinstance(self._last_errors_override, Exception):
                raise self._last_errors_override
            return self._last_errors_override
        return {"errors": self.error_logs[:limit]}

    async def export_logs(self, max_bytes: int = 1048576) -> bytes:
        """Return mock log content."""
        if self._export_logs_override is not None:
            if isinstance(self._export_logs_override, Exception):
                raise self._export_logs_override
            return self._export_logs_override
        return self.log_content[:max_bytes]

    async def get_guild_channels(self, guild_id: int) -> list[dict]:
        """Return text channels for a guild."""
        return self.channels_by_guild.get(guild_id, [])

    async def recheck_user(
        self, guild_id: int, user_id: int, admin_user_id: str | None = None
    ) -> dict:
        """Mock user recheck operation."""
        return {
            "status": "success",
            "message": "User rechecked successfully",
            "roles_updated": True,
        }


@pytest.fixture(autouse=True)
def fake_internal_api(monkeypatch):
    """Patch get_internal_api_client to return a fake client."""
    fake = FakeInternalAPIClient()

    # Override the FastAPI dependency injection
    from app import app
    from core.dependencies import get_internal_api_client

    app.dependency_overrides[get_internal_api_client] = lambda: fake

    yield fake

    # Cleanup
    app.dependency_overrides.clear()
