"""
Test configuration and fixtures for backend tests.
"""

import contextlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent

sys.path.insert(0, str(project_root))

# Add backend directory to path so we can import app
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from core import dependencies

from config.config_loader import ConfigLoader
from services.config_service import ConfigService
from services.db.database import Database


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
                (123, 'roles.discord_managers', '[\"999111225\"]'),
                (123, 'roles.moderators', '[\"999111223\"]'),
                (123, 'roles.event_coordinators', '[\"999111226\"]'),
                (123, 'roles.staff', '[\"999111224\"]'),
                (123, 'organization.sid', '\"TEST\"'),
                (1, 'roles.bot_admins', '[\"999111222\"]'),
                (1, 'roles.discord_managers', '[\"999111225\"]'),
                (1, 'roles.moderators', '[\"999111223\"]'),
                (1, 'roles.event_coordinators', '[\"999111226\"]'),
                (1, 'roles.staff', '[\"999111224\"]'),
                (2, 'roles.bot_admins', '[\"999111222\"]'),
                (2, 'roles.discord_managers', '[\"999111225\"]'),
                (2, 'roles.moderators', '[\"999111223\"]'),
                (2, 'roles.event_coordinators', '[\"999111226\"]'),
                (2, 'roles.staff', '[\"999111224\"]'),
                (999, 'roles.bot_admins', '[\"999111222\"]'),
                (999, 'roles.discord_managers', '[\"999111225\"]'),
                (999, 'roles.moderators', '[\"999111223\"]'),
                (999, 'roles.event_coordinators', '[\"999111226\"]'),
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
    # Ensure clean ConfigLoader state so CONFIG_PATH overrides apply per-test
    ConfigLoader.reset()

    # Seed backend dependencies because ASGITransport doesn't trigger lifespan in tests
    config_loader = ConfigLoader()
    dependencies._config_loader = config_loader

    config_service = ConfigService(config_loader=config_loader)
    await config_service.initialize()
    dependencies._config_service = config_service

    # Reset voice service singleton for fresh test state
    dependencies._voice_service = None

    # Initialize in-memory session store (lifespan won't run under ASGITransport)
    from core import session_store
    from core.rate_limit import limiter

    # Ensure a clean session store state for each test in case a previous test
    # aborted during setup/teardown.
    with contextlib.suppress(Exception):
        await session_store.close()

    await session_store.initialize()  # defaults to :memory:
    limiter.reset()  # clear rate-limit counters between tests

    # Import app after database and services are initialized
    from app import app

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await session_store.close()


@pytest_asyncio.fixture
async def mock_admin_session():
    """Create a mock session token for an admin user."""
    from core.security import create_session_token_async

    return await create_session_token_async(
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


@pytest_asyncio.fixture
async def mock_moderator_session():
    """Create a mock session token for a moderator user."""
    from core.security import create_session_token_async

    return await create_session_token_async(
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


@pytest_asyncio.fixture
async def mock_discord_manager_session():
    """Create a mock session token for a discord manager user."""
    from core.security import create_session_token_async

    return await create_session_token_async(
        {
            "user_id": "333222111",  # Discord manager test user
            "username": "TestDiscordManager",
            "discriminator": "0004",
            "avatar": None,
            "active_guild_id": "123",  # Default test guild
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "discord_manager",
                    "source": "discord_manager_role",
                },
            },
        }
    )


@pytest_asyncio.fixture
async def mock_event_coordinator_session():
    """Create a mock session token for an event coordinator user."""
    from core.security import create_session_token_async

    return await create_session_token_async(
        {
            "user_id": "444333222",
            "username": "TestEventCoordinator",
            "discriminator": "0005",
            "avatar": None,
            "active_guild_id": "123",
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "event_coordinator",
                    "source": "event_coordinator_role",
                },
            },
        }
    )


@pytest_asyncio.fixture
async def mock_staff_session():
    """Create a mock session token for a staff user."""
    from core.security import create_session_token_async

    return await create_session_token_async(
        {
            "user_id": "111222444",
            "username": "TestStaff",
            "discriminator": "0006",
            "avatar": None,
            "active_guild_id": "123",
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "staff",
                    "source": "staff_role",
                },
            },
        }
    )


@pytest_asyncio.fixture
async def mock_unauthorized_session():
    """Create a mock session token for an unauthorized user."""
    from core.security import create_session_token_async

    return await create_session_token_async(
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
        self.scheduled_events_by_guild: dict[int, list[dict]] = {}
        self.occupied_voice_channels: dict[int, list[dict]] = {}
        self.health_data: dict | None = None
        self.error_logs: list[dict] = []
        self.log_content: bytes = b"Mock log content\n"
        # Allow overriding method responses for specific tests
        self._health_report_override = None
        self._last_errors_override = None
        self._export_logs_override = None
        # Metrics overrides
        self._metrics_overview_override = None
        self._metrics_voice_lb_override = None
        self._metrics_msg_lb_override = None
        self._metrics_top_games_override = None
        self._metrics_game_override = None
        self._metrics_timeseries_override = None
        self._metrics_user_override = None
        self._metrics_delete_user_override = None

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

    @staticmethod
    def _required_validation_role_id(user_id: int) -> str:
        if user_id == 1428084144860303511:
            return "999111223"
        if user_id == 333222111:
            return "999111225"
        if user_id == 444333222:
            return "999111226"
        if user_id == 111222444:
            return "999111224"
        return "999111222"

    @staticmethod
    def _role_name_for_id(role_id: str) -> str:
        role_names = {
            "999111222": "Bot Admin",
            "999111223": "Moderator",
            "999111224": "Staff",
            "999111225": "Discord Manager",
            "999111226": "Event Coordinator",
        }
        return role_names.get(role_id, "Bot Admin")

    def _ensure_validation_role(self, member: dict, user_id: int) -> None:
        role_ids = member.setdefault("role_ids", [])
        if not role_ids and "roles" in member:
            role_ids.extend([r.get("id") for r in member["roles"] if r.get("id")])

        required_role_id = self._required_validation_role_id(user_id)
        if required_role_id not in role_ids:
            role_ids.append(required_role_id)

    async def get_guild_member(self, guild_id: int, user_id: int) -> dict:
        """Return single guild member data."""
        key = (guild_id, user_id)
        member_data = self.member_data.get(key)
        if member_data is None:
            try:
                normalized_key = (int(guild_id), int(user_id))
            except (TypeError, ValueError):
                normalized_key = None
            if normalized_key is not None:
                member_data = self.member_data.get(normalized_key)

        if member_data is not None:
            member = member_data.copy()
            member.setdefault("source", "discord")
            self._ensure_validation_role(member, user_id)
            return member

        required_role_id = self._required_validation_role_id(user_id)
        roles = [
            {
                "id": required_role_id,
                "name": self._role_name_for_id(required_role_id),
            }
        ]

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

    async def get_guild_scheduled_events(self, guild_id: int) -> list[dict]:
        """Return scheduled events for a guild."""
        return self.scheduled_events_by_guild.get(guild_id, [])

    async def create_guild_scheduled_event(self, guild_id: int, payload: dict) -> dict:
        """Create and store a mock scheduled event for a guild."""
        event = {
            "id": str(900000000000000000 + len(self.scheduled_events_by_guild.get(guild_id, []))),
            "name": payload.get("name"),
            "description": payload.get("description"),
            "scheduled_start_time": payload.get("scheduled_start_time"),
            "scheduled_end_time": payload.get("scheduled_end_time"),
            "status": "scheduled",
            "entity_type": payload.get("entity_type"),
            "channel_id": payload.get("channel_id"),
            "channel_name": "Mock Event Channel",
            "location": payload.get("location"),
            "user_count": 0,
            "creator_id": "444333222",
            "creator_name": "TestEventCoordinator",
            "image_url": None,
        }
        self.scheduled_events_by_guild.setdefault(guild_id, []).append(event)
        return event

    async def update_guild_scheduled_event(
        self, guild_id: int, event_id: int, payload: dict
    ) -> dict:
        """Update and return a mock scheduled event for a guild."""
        events = self.scheduled_events_by_guild.setdefault(guild_id, [])
        event_id_str = str(event_id)

        for index, event in enumerate(events):
            if event.get("id") != event_id_str:
                continue

            updated_event = {
                **event,
                "name": payload.get("name"),
                "description": payload.get("description"),
                "scheduled_start_time": payload.get("scheduled_start_time"),
                "scheduled_end_time": payload.get("scheduled_end_time"),
                "entity_type": payload.get("entity_type"),
                "channel_id": payload.get("channel_id"),
                "channel_name": "Mock Event Channel" if payload.get("channel_id") else None,
                "location": payload.get("location"),
            }
            events[index] = updated_event
            return updated_event

        raise RuntimeError("Scheduled event not found")

    async def get_voice_channel_members(self, voice_channel_id: int) -> list[int]:
        """Return member IDs in a voice channel (mock)."""
        # Return empty list by default - tests can override if needed
        return []

    async def get_occupied_voice_channels(self, guild_id: int) -> list[dict]:
        """Return occupied voice/stage channels for a guild (mock).

        Tests populate ``occupied_voice_channels`` dict keyed by guild_id.
        Accepts both int and str keys for convenience.
        """
        result = self.occupied_voice_channels.get(guild_id)
        if result is None:
            try:
                result = self.occupied_voice_channels.get(int(guild_id))
            except (TypeError, ValueError):
                result = None
        return result or []

    async def recheck_user(
        self, guild_id: int, user_id: int, admin_user_id: str | None = None
    ) -> dict:
        """Mock user recheck operation."""
        return {
            "status": "success",
            "message": "User rechecked successfully",
            "roles_updated": True,
        }

    async def resend_verification_message(self, guild_id: int) -> dict:
        """Mock verification message resend operation.

        Tests can force this method to fail by setting
        ``fake_internal_api.raise_on_resend_verification_message = True``.
        """
        if getattr(self, "raise_on_resend_verification_message", False):
            raise RuntimeError("Failed to resend verification message (test)")

        return {
            "status": "success",
            "message": "Verification message resent",
        }

    async def deploy_ticket_panel(
        self, guild_id: int, *, channel_id: str | None = None,
    ) -> dict:
        """Mock ticket panel deployment."""
        return {"success": True, "message_id": "000000000"}

    # ------------------------------------------------------------------
    # Metrics endpoints
    # ------------------------------------------------------------------
    async def get_metrics_overview(
        self, guild_id: int, days: int = 7, user_ids: list[int] | None = None
    ) -> dict:
        """Return metrics overview data."""
        if self._metrics_overview_override is not None:
            if isinstance(self._metrics_overview_override, Exception):
                raise self._metrics_overview_override
            return self._metrics_overview_override
        return {
            "live": {
                "messages_today": 42,
                "active_voice_users": 3,
                "top_game": "Star Citizen",
                "active_game_sessions": 5,
            },
            "period": {
                "total_messages": 1200,
                "unique_messagers": 25,
                "avg_messages_per_user": 48.0,
                "total_voice_seconds": 360000,
                "unique_voice_users": 18,
                "avg_voice_per_user": 20000,
                "unique_users": 30,
                "top_games": [],
            },
        }

    async def get_metrics_voice_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return voice leaderboard data."""
        if self._metrics_voice_lb_override is not None:
            if isinstance(self._metrics_voice_lb_override, Exception):
                raise self._metrics_voice_lb_override
            return self._metrics_voice_lb_override
        return {
            "entries": [
                {"user_id": 123456789, "value": 7200.0},
                {"user_id": 987654321, "value": 3600.0},
            ]
        }

    async def get_metrics_message_leaderboard(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return message leaderboard data."""
        if self._metrics_msg_lb_override is not None:
            if isinstance(self._metrics_msg_lb_override, Exception):
                raise self._metrics_msg_lb_override
            return self._metrics_msg_lb_override
        return {
            "entries": [
                {"user_id": 123456789, "value": 500},
                {"user_id": 987654321, "value": 250},
            ]
        }

    async def get_metrics_top_games(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return top games data."""
        if self._metrics_top_games_override is not None:
            if isinstance(self._metrics_top_games_override, Exception):
                raise self._metrics_top_games_override
            return self._metrics_top_games_override
        return {
            "games": [
                {
                    "game_name": "Star Citizen",
                    "total_seconds": 72000,
                    "session_count": 20,
                    "avg_seconds": 3600,
                    "unique_players": 10,
                },
                {
                    "game_name": "Elite Dangerous",
                    "total_seconds": 36000,
                    "session_count": 10,
                    "avg_seconds": 3600,
                    "unique_players": 5,
                },
            ]
        }

    async def get_metrics_timeseries(
        self,
        guild_id: int,
        metric: str = "messages",
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return time-series data."""
        if self._metrics_timeseries_override is not None:
            if isinstance(self._metrics_timeseries_override, Exception):
                raise self._metrics_timeseries_override
            return self._metrics_timeseries_override
        return {
            "metric": metric,
            "days": days,
            "data": [
                {"hour": "2025-01-01T00:00:00", "value": 10.0},
                {"hour": "2025-01-01T01:00:00", "value": 15.0},
            ],
        }

    async def get_metrics_game(
        self,
        guild_id: int,
        game_name: str,
        days: int = 7,
        limit: int = 5,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return detailed metrics for one game."""
        if self._metrics_game_override is not None:
            if isinstance(self._metrics_game_override, Exception):
                raise self._metrics_game_override
            return self._metrics_game_override
        return {
            "game_name": game_name,
            "days": days,
            "total_seconds": 54000,
            "session_count": 15,
            "avg_seconds": 3600,
            "unique_players": 7,
            "top_players": [
                {
                    "user_id": 123456789,
                    "total_seconds": 7200,
                    "session_count": 3,
                    "avg_seconds": 2400,
                    "username": "PilotOne",
                },
                {
                    "user_id": 987654321,
                    "total_seconds": 5400,
                    "session_count": 2,
                    "avg_seconds": 2700,
                    "username": "PilotTwo",
                },
            ],
            "timeseries": [
                {"timestamp": 1735689600, "value": 3600, "unique_users": 3},
                {"timestamp": 1735693200, "value": 5400, "unique_users": 4},
            ],
        }

    async def get_metrics_user(
        self,
        guild_id: int,
        user_id: int,
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return per-user metrics data."""
        if self._metrics_user_override is not None:
            if isinstance(self._metrics_user_override, Exception):
                raise self._metrics_user_override
            return self._metrics_user_override
        return {
            "user_id": str(user_id),
            "total_messages": 150,
            "total_voice_seconds": 36000,
            "avg_messages_per_day": 21.4,
            "avg_voice_per_day": 5143,
            "top_games": [
                {
                    "game_name": "Star Citizen",
                    "total_seconds": 14400,
                }
            ],
            "timeseries": [
                {
                    "timestamp": 1735689600,
                    "messages": 5,
                    "voice_seconds": 1800,
                }
            ],
        }

    async def delete_metrics_user(self, guild_id: int, user_id: int) -> dict:
        """Delete per-user metrics data."""
        if self._metrics_delete_user_override is not None:
            if isinstance(self._metrics_delete_user_override, Exception):
                raise self._metrics_delete_user_override
            return self._metrics_delete_user_override
        return {
            "deleted": {
                "messages": 10,
                "voice_sessions": 3,
                "game_sessions": 2,
            }
        }

    async def get_activity_groups(
        self,
        guild_id: int,
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        """Return activity group counts."""
        tier_counts = {
            "hardcore": 2,
            "regular": 5,
            "casual": 8,
            "reserve": 10,
            "inactive": 25,
        }
        return {
            "all": tier_counts,
            "voice": tier_counts,
            "chat": tier_counts,
            "game": tier_counts,
        }

    async def get_activity_group_members(
        self, guild_id: int, dimension: str, tier: str
    ) -> dict:
        """Return user IDs for a specific activity tier."""
        return {
            "dimension": dimension,
            "tier": tier,
            "user_ids": [123456789, 987654321],
        }

    async def get_activity_group_members_bulk(
        self,
        guild_id: int,
        dimensions: list[str],
        tiers: list[str],
        days: int = 30,
    ) -> dict[str, dict[str, list[int]]]:
        """Return user IDs for multiple dimension+tier combos."""
        result: dict[str, dict[str, list[int]]] = {}
        for dim in dimensions:
            tier_map: dict[str, list[int]] = {}
            for t in tiers:
                tier_map[t] = [123456789, 987654321]
            result[dim] = tier_map
        return result


@pytest.fixture(autouse=True)
def fake_internal_api(monkeypatch):
    """Patch get_internal_api_client to return a fake client."""
    fake = FakeInternalAPIClient()

    # Ensure user detail cache does not leak across tests.
    from routes.users import _member_cache

    _member_cache.clear()

    # Populate guild members for privacy filtering tests
    # These are the test users added to the verification table in temp_db
    # plus additional users used in specific tests
    # Guild 123 is the default test guild used in mock sessions
    fake.members_by_guild[123] = [
        {"user_id": 123456789},
        {"user_id": 987654321},
        {"user_id": 111222333},
        {"user_id": 444555666},
        {"user_id": 555555555},  # Unverified user for voice settings tests
        {"user_id": 246604397155581954},  # Admin user from test sessions
        {"user_id": 333222111},  # Discord manager user
        {"user_id": 1428084144860303511},  # Moderator user
    ]

    # Override the FastAPI dependency injection
    from app import app
    from core.dependencies import get_internal_api_client

    app.dependency_overrides[get_internal_api_client] = lambda: fake

    yield fake

    # Cleanup
    _member_cache.clear()
    app.dependency_overrides.clear()
