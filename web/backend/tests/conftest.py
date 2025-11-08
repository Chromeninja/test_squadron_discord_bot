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

    # Initialize database
    await Database.initialize(db_path)

    # Seed some test data
    async with Database.get_connection() as db:
        # Add test verification records
        await db.execute(
            """
            INSERT INTO verification 
            (user_id, rsi_handle, membership_status, last_updated, community_moniker)
            VALUES 
                (123456789, 'TestUser1', 'main', 1234567890, 'Test Main'),
                (987654321, 'TestUser2', 'affiliate', 1234567891, 'Test Affiliate'),
                (111222333, 'TestUser3', 'non_member', 1234567892, NULL),
                (444555666, 'TestUser4', 'unknown', 1234567893, NULL)
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
