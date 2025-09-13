"""
Tests for the service architecture.
"""

import contextlib
import tempfile
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from services import (
    ConfigService,
    GuildService,
    HealthService,
    ServiceManager,
    VoiceService,
)
from services.db.database import Database


@pytest_asyncio.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    await Database.initialize(db_path)
    yield db_path

    # Cleanup
    from pathlib import Path

    with contextlib.suppress(OSError):
        Path(db_path).unlink()


@pytest.fixture
async def service_manager(temp_db):
    """Create a service manager with temporary database."""
    manager = ServiceManager()
    await manager.initialize()
    yield manager
    await manager.shutdown()


class TestConfigService:
    """Tests for ConfigService."""

    @pytest.mark.asyncio
    async def test_config_service_initialization(self, temp_db):
        """Test config service initializes correctly."""
        config_service = ConfigService()
        await config_service.initialize()

        assert config_service._initialized
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_guild_setting_storage(self, temp_db):
        """Test storing and retrieving guild settings."""
        # Force reinitialization with the test database
        Database._initialized = False
        Database._db_path = temp_db
        await Database.initialize(temp_db)

        config_service = ConfigService()
        await config_service.initialize()

        guild_id = 12345
        key = "test.setting"
        value = {"nested": "value"}

        # Set setting
        await config_service.set_guild_setting(guild_id, key, value)

        # Get setting
        retrieved = await config_service.get_guild_setting(guild_id, key)
        print(f"DEBUG: Set {value}, got back: {retrieved}")
        assert retrieved == value

        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_nested_key_access(self, temp_db):
        """Test accessing nested configuration keys."""
        config_service = ConfigService()
        await config_service.initialize()

        # Set global config after initialization (since initialization loads from file)
        config_service._global_config = {"roles": {"admin": 123456}}

        # Test nested key access
        value = await config_service.get_global_setting("roles.admin")
        assert value == 123456

        # Test non-existent key
        value = await config_service.get_global_setting("roles.nonexistent", "default")
        assert value == "default"

        await config_service.shutdown()


class TestGuildService:
    """Tests for GuildService."""

    @pytest.mark.asyncio
    async def test_guild_service_initialization(self, temp_db):
        """Test guild service initializes correctly."""
        config_service = ConfigService()
        await config_service.initialize()

        guild_service = GuildService(config_service)
        await guild_service.initialize()

        assert guild_service._initialized

        await guild_service.shutdown()
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_guild_registration(self, temp_db):
        """Test registering a guild."""
        # Force reinitialization with the test database
        Database._initialized = False
        Database._db_path = temp_db
        await Database.initialize(temp_db)

        config_service = ConfigService()
        await config_service.initialize()

        guild_service = GuildService(config_service)
        await guild_service.initialize()

        # Create mock guild
        guild = MagicMock()
        guild.id = 12345
        guild.name = "Test Guild"
        guild.roles = []

        # Register guild (just test that it doesn't crash)
        await guild_service.register_guild(guild)

        # Guild registration successful if no exception raised
        assert True

        await guild_service.shutdown()
        await config_service.shutdown()


class TestHealthService:
    """Tests for HealthService."""

    @pytest.mark.asyncio
    async def test_health_service_initialization(self, temp_db):
        """Test health service initializes correctly."""
        health_service = HealthService()
        await health_service.initialize()

        assert health_service._initialized
        await health_service.shutdown()

    @pytest.mark.asyncio
    async def test_metric_recording(self, temp_db):
        """Test metric recording functionality."""
        health_service = HealthService()
        await health_service.initialize()

        # Record some metrics
        await health_service.record_metric("test_metric", 5)
        await health_service.record_metric("test_metric", 3)

        # Check metrics are recorded
        async with health_service._metrics_lock:
            assert health_service._metrics["test_metric"] == 8

        await health_service.shutdown()

    @pytest.mark.asyncio
    async def test_system_info(self, temp_db):
        """Test system information gathering."""
        health_service = HealthService()
        await health_service.initialize()

        system_info = await health_service.get_system_info()

        # Check required fields are present
        required_fields = [
            "cpu_percent",
            "memory_mb",
            "memory_percent",
            "threads",
            "uptime_seconds",
        ]
        for field in required_fields:
            assert field in system_info
            assert isinstance(system_info[field], int | float)

        await health_service.shutdown()


class TestVoiceService:
    """Tests for VoiceService."""

    @pytest.mark.asyncio
    async def test_voice_service_initialization(self, temp_db):
        """Test voice service initializes correctly."""
        config_service = ConfigService()
        await config_service.initialize()

        voice_service = VoiceService(config_service)
        await voice_service.initialize()

        assert voice_service._initialized

        await voice_service.shutdown()
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_can_create_voice_channel(self, temp_db):
        """Test voice channel creation validation."""
        # Force reinitialization with the test database
        Database._initialized = False
        Database._db_path = temp_db
        await Database.initialize(temp_db)

        config_service = ConfigService()
        await config_service.initialize()

        voice_service = VoiceService(config_service)
        await voice_service.initialize()

        guild_id = 12345
        jtc_channel_id = 67890
        user_id = 111

        # Test creation when allowed
        can_create, reason = await voice_service.can_create_voice_channel(
            guild_id, jtc_channel_id, user_id
        )

        # Should be able to create since no existing channel
        assert can_create is True

        await voice_service.shutdown()
        await config_service.shutdown()


class TestServiceManager:
    """Tests for ServiceManager."""

    @pytest.mark.asyncio
    async def test_service_manager_initialization(self, temp_db):
        """Test service manager initializes all services."""
        manager = ServiceManager()
        await manager.initialize()

        assert manager.is_initialized

        # Check all services are available
        assert manager.config is not None
        assert manager.guild is not None
        assert manager.health is not None
        assert manager.voice is not None

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_service_access(self, temp_db):
        """Test accessing services through manager."""
        manager = ServiceManager()
        await manager.initialize()

        # Test getting services by name
        config_service = manager.get_service("config")
        assert isinstance(config_service, ConfigService)

        guild_service = manager.get_service("guild")
        assert isinstance(guild_service, GuildService)

        # Test getting all services
        all_services = manager.get_all_services()
        assert len(all_services) == 4

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_all(self, temp_db):
        """Test comprehensive health checking."""
        manager = ServiceManager()
        await manager.initialize()

        health_report = await manager.health_check_all()

        assert "status" in health_report
        assert "services" in health_report

        # Check all services are reported
        services = health_report["services"]
        assert "config" in services
        assert "guild" in services
        assert "health" in services
        assert "voice" in services

        await manager.shutdown()


@pytest.mark.asyncio
async def test_integration_flow(temp_db):
    """Test complete service integration flow."""
    # Force reinitialization with the test database
    Database._initialized = False
    Database._db_path = temp_db
    await Database.initialize(temp_db)

    manager = ServiceManager()
    await manager.initialize()

    guild_id = 12345

    # Test configuration
    await manager.config.set_guild_setting(guild_id, "voice.cooldown_seconds", 10)
    cooldown = await manager.config.get_guild_setting(
        guild_id, "voice.cooldown_seconds"
    )
    assert cooldown == 10

    # Test health checks (using base health_check method)
    health_status = await manager.health.health_check()
    assert health_status["status"] == "healthy"

    # Test service access
    assert manager.config is not None
    assert manager.guild is not None
    assert manager.health is not None
    assert manager.voice is not None

    await manager.shutdown()


if __name__ == "__main__":
    pytest.main([__file__])
