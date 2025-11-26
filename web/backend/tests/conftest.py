"""
Test configuration and fixtures for backend tests.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
import sys

sys.path.insert(0, str(project_root))

# Add backend directory to path so we can import app
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

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
        # Add test verification records
        await db.execute(
            """
            INSERT INTO verification 
            (user_id, rsi_handle, membership_status, last_updated, 
             community_moniker, main_orgs, affiliate_orgs)
            VALUES 
                (123456789, 'TestUser1', 'main', 1234567890, 
                 'Test Main', '["TEST"]', '[]'),
                (987654321, 'TestUser2', 'affiliate', 1234567891, 
                 'Test Affiliate', '[]', '["TEST"]'),
                (111222333, 'TestUser3', 'non_member', 1234567892, 
                 NULL, '[]', '[]'),
                (444555666, 'TestUser4', 'unknown', 1234567893, 
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
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest_asyncio.fixture
async def client(temp_db):
    """Create a test client for the FastAPI app."""
    # Import app after database is initialized
    from app import app

    async with AsyncClient(app=app, base_url="http://test") as ac:
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
            "is_admin": True,
            "is_moderator": False,
            "active_guild_id": "123",  # Default test guild
            "authorized_guild_ids": [1, 2],  # Include authorized guilds for filtering
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
            "is_admin": False,
            "is_moderator": True,
            "active_guild_id": "123",  # Default test guild
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
            "is_admin": False,
            "is_moderator": False,
        }
    )


class FakeInternalAPIClient:
    """Simple fake internal API client for tests."""

    def __init__(self):
        self.guilds: list[dict] = []
        self.roles_by_guild: dict[int, list[dict]] = {}
        self.guild_stats: dict[int, dict] = {}
        self.members_by_guild: dict[int, list[dict]] = {}
        self.member_data: dict[tuple[int, int], dict] = {}  # (guild_id, user_id) -> member_data

    async def get_guilds(self) -> list[dict]:
        return self.guilds

    async def get_guild_roles(self, guild_id: int) -> list[dict]:
        return self.roles_by_guild.get(guild_id, [])

    async def get_guild_stats(self, guild_id: int) -> dict:
        """Return guild stats or default values."""
        return self.guild_stats.get(guild_id, {
            "guild_id": guild_id,
            "member_count": 100,  # Default test value
            "approximate_member_count": None
        })

    async def get_guild_members(self, guild_id: int, page: int = 1, page_size: int = 100) -> dict:
        """Return paginated guild members."""
        members = self.members_by_guild.get(guild_id, [])
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_members = members[start_idx:end_idx]

        return {
            "members": page_members,
            "page": page,
            "page_size": page_size,
            "total": len(members)
        }

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict:
        """Return single guild member data."""
        key = (guild_id, user_id)
        if key in self.member_data:
            return self.member_data[key]

        # Default member data
        return {
            "user_id": user_id,
            "username": f"User{user_id}",
            "discriminator": "0001",
            "global_name": f"User {user_id}",
            "avatar_url": None,
            "joined_at": "2024-01-01T00:00:00",
            "created_at": "2023-01-01T00:00:00",
            "roles": []
        }


@pytest.fixture
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
